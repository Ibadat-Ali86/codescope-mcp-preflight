"""Read-only semantic and symbol query orchestration."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Final, Literal, Protocol

import numpy as np
from numpy.typing import NDArray
from pydantic import ValidationError

from codescope.config import AppConfig, StorageConfig
from codescope.embedder import LocalEmbedder
from codescope.exceptions import (
    CodeScopeError,
    IndexNotFoundError,
    InvalidLimitError,
    InvalidQueryError,
    QueryFailedError,
    StorageFailedError,
)
from codescope.indexer import RepositoryIndexer
from codescope.models import IndexStatus, SearchResult, Symbol, SymbolResult
from codescope.storage import ChromaStorage, StoredChunkMatch
from codescope.utils.language import SupportedLanguage, normalize_language

type SymbolKind = Literal["function", "async_function", "class", "method"]
type StatusProvider = Callable[[], IndexStatus]

_QUERY_ERROR: Final = "The repository query could not be completed safely."
_INVALID_QUERY_ERROR: Final = "The query is invalid or outside the safe length bounds."
_INVALID_SYMBOL_ERROR: Final = "The symbol name is invalid or outside the safe length bounds."
_INVALID_KIND_ERROR: Final = "The symbol kind is unsupported."
_INDEX_ERROR: Final = "No complete usable CodeScope index exists."
_MAX_QUERY_CHARACTERS: Final = 16_384
_MAX_SYMBOL_NAME_CHARACTERS: Final = 1_024
_MAX_SNIPPET_CHARACTERS: Final = 8_192
_SYMBOL_KINDS: Final[tuple[SymbolKind, ...]] = (
    "function",
    "async_function",
    "class",
    "method",
)


class _EmbeddingBackend(Protocol):
    @property
    def embedding_dimension(self) -> int: ...

    def encode(self, texts: Sequence[str]) -> NDArray[np.float32]: ...


class _QueryStorage(Protocol):
    def query(
        self,
        query_embedding: NDArray[np.generic],
        *,
        limit: int,
        language: str | None = None,
    ) -> list[StoredChunkMatch]: ...

    def read_symbols(self) -> list[Symbol]: ...

    def close(self) -> None: ...


class _StorageFactory(Protocol):
    def __call__(
        self,
        config: StorageConfig,
        *,
        create: bool = True,
    ) -> _QueryStorage: ...


def _default_storage_factory(
    config: StorageConfig,
    *,
    create: bool = True,
) -> _QueryStorage:
    return ChromaStorage(config, create=create)


class QueryEngine:
    """Serve validated read-only queries over one persisted CodeScope index."""

    def __init__(
        self,
        config: AppConfig,
        *,
        embedder: _EmbeddingBackend | None = None,
        storage_factory: _StorageFactory = _default_storage_factory,
        status_provider: StatusProvider | None = None,
    ) -> None:
        """Store lazy collaborators without opening storage or loading a model.

        Args:
            config: Immutable application and query configuration.
            embedder: Optional deterministic or already managed embedding backend.
            storage_factory: Read-only storage construction boundary.
            status_provider: Authoritative Phase 5 index-status validation boundary.
        """
        self._config = config
        self._embedder = embedder
        self._storage_factory = storage_factory
        self._status_provider = status_provider or RepositoryIndexer(config).status

    def search_code(
        self,
        query: str,
        language: str | None = None,
        limit: int = 5,
    ) -> list[SearchResult]:
        """Return deterministic semantic evidence from persisted source chunks."""
        self._validated_status()
        normalized_query = self._validate_query(query)
        normalized_language = self._validate_language(language)
        validated_limit = self._validate_limit(limit)
        return self._semantic_search(
            normalized_query,
            language=normalized_language,
            limit=validated_limit,
        )

    def find_symbol(
        self,
        name: str,
        kind: str | None = None,
        limit: int = 20,
    ) -> list[SymbolResult]:
        """Return exact and partial matches from validated persisted symbol metadata."""
        status = self._validated_status()
        normalized_name = self._validate_symbol_name(name)
        normalized_kind = self._validate_kind(kind)
        validated_limit = self._validate_limit(limit)
        symbols = self._read_symbols(expected_count=status.total_symbols)
        return self._rank_symbols(
            symbols,
            name=normalized_name,
            kind=normalized_kind,
            limit=validated_limit,
        )

    def find_similar(
        self,
        code_snippet: str,
        language: str | None = None,
        limit: int = 3,
    ) -> list[SearchResult]:
        """Return similar stored code evidence for a proposed implementation.

        A high similarity score means inspect the existing implementation first. It
        does not prove that the two implementations are behaviorally identical.
        """
        self._validated_status()
        normalized_snippet = self._validate_query(code_snippet)
        normalized_language = self._validate_language(language)
        validated_limit = self._validate_limit(limit)
        return self._semantic_search(
            normalized_snippet,
            language=normalized_language,
            limit=validated_limit,
        )

    def get_index_status(self) -> IndexStatus:
        """Return the authoritative validated Phase 5 index status."""
        return self._validated_status()

    def _validated_status(self) -> IndexStatus:
        try:
            status = self._status_provider()
        except CodeScopeError:
            raise
        except (OSError, RuntimeError, TypeError, UnicodeError, ValueError) as error:
            raise QueryFailedError(_QUERY_ERROR) from error
        if not isinstance(status, IndexStatus) or not status.index_exists:
            raise IndexNotFoundError(_INDEX_ERROR)
        return status

    def _semantic_search(
        self,
        text: str,
        *,
        language: SupportedLanguage | None,
        limit: int,
    ) -> list[SearchResult]:
        vector = self._encode_query(text)
        storage = self._open_storage()
        try:
            matches = storage.query(vector, limit=limit, language=language)
        except CodeScopeError:
            raise
        except (OSError, RuntimeError, TypeError, UnicodeError, ValueError) as error:
            raise QueryFailedError(_QUERY_ERROR) from error
        finally:
            storage.close()
        return self._convert_matches(matches, limit=limit)

    def _encode_query(self, text: str) -> NDArray[np.float32]:
        embedder = self._embedder
        if embedder is None:
            embedder = LocalEmbedder(self._config.embeddings, allow_download=False)
            self._embedder = embedder
        try:
            expected_dimension = embedder.embedding_dimension
            vectors = embedder.encode((text,))
        except CodeScopeError:
            raise
        except (OSError, RuntimeError, TypeError, UnicodeError, ValueError) as error:
            raise QueryFailedError(
                _QUERY_ERROR,
                suggestion="Prepare the configured embedding model locally and retry.",
            ) from error
        if (
            not isinstance(expected_dimension, int)
            or isinstance(expected_dimension, bool)
            or expected_dimension <= 0
            or not isinstance(vectors, np.ndarray)
            or vectors.ndim != 2
            or vectors.shape != (1, expected_dimension)
            or not np.issubdtype(vectors.dtype, np.number)
        ):
            raise QueryFailedError(_QUERY_ERROR)
        try:
            result = vectors.astype(np.float32, copy=False)
        except (TypeError, ValueError) as error:
            raise QueryFailedError(_QUERY_ERROR) from error
        if not np.isfinite(result).all():
            raise QueryFailedError(_QUERY_ERROR)
        return result

    def _open_storage(self) -> _QueryStorage:
        try:
            return self._storage_factory(self._config.storage, create=False)
        except CodeScopeError:
            raise
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            raise StorageFailedError(
                "Local index storage could not complete the requested operation."
            ) from error

    def _read_symbols(self, *, expected_count: int) -> list[Symbol]:
        storage = self._open_storage()
        try:
            symbols = storage.read_symbols()
        except CodeScopeError:
            raise
        except (OSError, RuntimeError, TypeError, UnicodeError, ValueError) as error:
            raise QueryFailedError(_QUERY_ERROR) from error
        finally:
            storage.close()
        if len(symbols) != expected_count or any(
            not isinstance(symbol, Symbol) for symbol in symbols
        ):
            raise IndexNotFoundError(_INDEX_ERROR)
        return symbols

    @staticmethod
    def _convert_matches(
        matches: Sequence[StoredChunkMatch],
        *,
        limit: int,
    ) -> list[SearchResult]:
        if isinstance(matches, (str, bytes)) or not isinstance(matches, Sequence):
            raise QueryFailedError(_QUERY_ERROR)
        if len(matches) > limit:
            raise QueryFailedError(_QUERY_ERROR)
        converted: list[tuple[SearchResult, str]] = []
        try:
            for match in matches:
                if not isinstance(match, StoredChunkMatch) or not math.isfinite(match.distance):
                    raise ValueError(_QUERY_ERROR)
                score = max(0.0, min(1.0, 1.0 - match.distance))
                result = SearchResult(
                    file=match.file,
                    start_line=match.start_line,
                    end_line=match.end_line,
                    symbol=match.symbol_name,
                    qualified_name=match.qualified_name,
                    language=match.language,
                    snippet=match.text[:_MAX_SNIPPET_CHARACTERS],
                    relevance_score=score,
                )
                converted.append((result, match.id))
        except (TypeError, ValueError, ValidationError) as error:
            raise QueryFailedError(_QUERY_ERROR) from error
        converted.sort(
            key=lambda item: (
                -item[0].relevance_score,
                item[0].file,
                item[0].start_line,
                item[0].end_line,
                item[0].qualified_name or item[0].symbol or "",
                item[1],
            )
        )
        return [item[0] for item in converted]

    @staticmethod
    def _rank_symbols(
        symbols: Sequence[Symbol],
        *,
        name: str,
        kind: SymbolKind | None,
        limit: int,
    ) -> list[SymbolResult]:
        folded_name = name.casefold()
        ranked: list[tuple[int, tuple[object, ...], Symbol]] = []
        seen: set[tuple[object, ...]] = set()
        for symbol in symbols:
            if kind is not None and symbol.kind != kind:
                continue
            rank = QueryEngine._symbol_rank(symbol, name=name, folded_name=folded_name)
            if rank is None:
                continue
            identity = (
                symbol.name,
                symbol.qualified_name,
                symbol.kind,
                symbol.file,
                symbol.start_line,
                symbol.end_line,
                symbol.signature,
                symbol.docstring,
            )
            if identity in seen:
                continue
            seen.add(identity)
            tie_breaker: tuple[object, ...] = (
                symbol.qualified_name.casefold(),
                symbol.name.casefold(),
                symbol.file,
                symbol.start_line,
                symbol.end_line,
                symbol.kind,
                symbol.qualified_name,
                symbol.name,
                symbol.signature,
                symbol.docstring or "",
            )
            ranked.append((rank, tie_breaker, symbol))
        ranked.sort(key=lambda item: (item[0], item[1]))
        try:
            return [
                SymbolResult(
                    name=symbol.name,
                    qualified_name=symbol.qualified_name,
                    kind=symbol.kind,
                    file=symbol.file,
                    start_line=symbol.start_line,
                    end_line=symbol.end_line,
                    signature=symbol.signature,
                    docstring=symbol.docstring,
                )
                for _, _, symbol in ranked[:limit]
            ]
        except (TypeError, ValueError, ValidationError) as error:
            raise QueryFailedError(_QUERY_ERROR) from error

    @staticmethod
    def _symbol_rank(symbol: Symbol, *, name: str, folded_name: str) -> int | None:
        if symbol.name == name:
            return 0
        if symbol.name.casefold() == folded_name:
            return 1
        if symbol.qualified_name == name:
            return 2
        if symbol.name.casefold().startswith(
            folded_name
        ) or symbol.qualified_name.casefold().startswith(folded_name):
            return 3
        if folded_name in symbol.name.casefold() or folded_name in symbol.qualified_name.casefold():
            return 4
        return None

    def _validate_query(self, value: object) -> str:
        if not isinstance(value, str):
            raise InvalidQueryError(_INVALID_QUERY_ERROR)
        normalized = value.strip()
        if (
            len(normalized) < self._config.search.minimum_query_characters
            or len(normalized) > _MAX_QUERY_CHARACTERS
        ):
            raise InvalidQueryError(_INVALID_QUERY_ERROR)
        return normalized

    @staticmethod
    def _validate_symbol_name(value: object) -> str:
        if not isinstance(value, str):
            raise InvalidQueryError(_INVALID_SYMBOL_ERROR)
        normalized = value.strip()
        if not normalized or len(normalized) > _MAX_SYMBOL_NAME_CHARACTERS:
            raise InvalidQueryError(_INVALID_SYMBOL_ERROR)
        return normalized

    def _validate_limit(self, value: object) -> int:
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 1
            or value > self._config.search.maximum_limit
        ):
            raise InvalidLimitError("The result limit is outside the configured range.")
        return value

    @staticmethod
    def _validate_language(value: object) -> SupportedLanguage | None:
        if value is None:
            return None
        if not isinstance(value, str):
            return normalize_language("")
        return normalize_language(value)

    @staticmethod
    def _validate_kind(value: object) -> SymbolKind | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise InvalidQueryError(_INVALID_KIND_ERROR)
        normalized = value.strip().casefold()
        if normalized not in _SYMBOL_KINDS:
            raise InvalidQueryError(
                _INVALID_KIND_ERROR,
                suggestion="Use function, async_function, class, or method.",
            )
        return normalized
