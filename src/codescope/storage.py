"""Persistent local Chroma storage and atomic CodeScope metadata."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath, PureWindowsPath
from types import MappingProxyType
from typing import Annotated, Final, Literal, Self, cast

import chromadb
import numpy as np
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from chromadb.api.types import Metadata, Where
from chromadb.config import Settings
from chromadb.errors import ChromaError, NotFoundError
from numpy.typing import NDArray
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_serializer,
    field_validator,
    model_validator,
)

from codescope.config import StorageConfig
from codescope.exceptions import InvalidPathError, StorageFailedError
from codescope.models import CodeChunk, Symbol
from codescope.utils.json_io import (
    atomic_write_metadata_json,
    read_metadata_json,
    remove_metadata_file,
)
from codescope.utils.language import normalize_language
from codescope.utils.path_guard import validate_runtime_directory

_CHROMA_DIRECTORY: Final = "chroma"
_SYMBOLS_FILE: Final = "symbols.json"
_INDEX_METADATA_FILE: Final = "index_meta.json"
_STORAGE_ERROR: Final = "Local index storage could not complete the requested operation."
_MISSING_COLLECTION_ERROR: Final = "The local CodeScope index is not initialized."
_INPUT_ERROR: Final = "Storage input is invalid."
_INDEX_SCHEMA: Final = "codescope-index-v1"

NonNegativeInt = Annotated[int, Field(ge=0)]
FiniteDistance = Annotated[float, Field(allow_inf_nan=False)]


class _InternalStorageModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


def _validate_required_text(value: str) -> str:
    if not value.strip():
        raise ValueError(_INPUT_ERROR)
    return value


def _validate_public_path(value: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value or "\\" in value:
        raise ValueError(_INPUT_ERROR)
    segments = value.split("/")
    windows_path = PureWindowsPath(value)
    if (
        PurePosixPath(value).is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or any(segment in {"", ".", ".."} for segment in segments)
    ):
        raise ValueError(_INPUT_ERROR)
    return value


class StoredChunkMatch(_InternalStorageModel):
    """Immutable internal result from a Chroma vector query."""

    id: str
    text: str
    file: str
    start_line: int
    end_line: int
    language: Literal["python"]
    symbol_name: str | None
    qualified_name: str | None
    chunk_index: NonNegativeInt
    content_hash: str
    distance: FiniteDistance

    @field_validator("id", "text", "content_hash")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return _validate_required_text(value)

    @field_validator("file")
    @classmethod
    def validate_file(cls, value: str) -> str:
        return _validate_public_path(value)

    @model_validator(mode="after")
    def validate_lines(self) -> Self:
        if self.start_line < 1 or self.end_line < self.start_line:
            raise ValueError(_INPUT_ERROR)
        return self


class IndexMetadata(_InternalStorageModel):
    """Internal on-disk index metadata; not part of the public MCP contract."""

    schema_version: Literal["codescope-index-v1"] = _INDEX_SCHEMA
    codescope_version: str
    index_root: str
    embedding_model: str
    timestamp: str
    file_count: NonNegativeInt
    symbol_count: NonNegativeInt
    chunk_count: NonNegativeInt
    language_counts: Mapping[str, int]
    configuration_fingerprint: str

    @field_validator("codescope_version", "embedding_model", "timestamp")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return _validate_required_text(value)

    @field_validator("index_root")
    @classmethod
    def validate_index_root(cls, value: str) -> str:
        if value == ".":
            return value
        return _validate_public_path(value)

    @field_validator("configuration_fingerprint")
    @classmethod
    def validate_fingerprint(cls, value: str) -> str:
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError(_INPUT_ERROR)
        return value

    @field_validator("language_counts", mode="after")
    @classmethod
    def freeze_language_counts(cls, value: Mapping[str, int]) -> Mapping[str, int]:
        if any(not key.strip() for key in value) or any(count < 0 for count in value.values()):
            raise ValueError(_INPUT_ERROR)
        return MappingProxyType(dict(value))

    @field_serializer("language_counts")
    def serialize_language_counts(self, value: Mapping[str, int]) -> dict[str, int]:
        return dict(value)


class ChromaStorage:
    """Persistent local storage for immutable CodeScope source chunks."""

    def __init__(self, config: StorageConfig) -> None:
        """Create one telemetry-disabled local persistent client.

        Args:
            config: Validated runtime path and collection identity.

        Raises:
            StorageFailedError: If the local runtime cannot be opened safely.
        """
        self._config = config
        self._settings = Settings(anonymized_telemetry=False, allow_reset=False)
        try:
            self._runtime_root = validate_runtime_directory(config.path, create=True)
            self._chroma_path = validate_runtime_directory(
                self._runtime_root / _CHROMA_DIRECTORY,
                create=True,
            )
            self._client: ClientAPI = chromadb.PersistentClient(
                path=self._chroma_path,
                settings=self._settings,
            )
        except (ChromaError, InvalidPathError, OSError, RuntimeError, ValueError) as error:
            raise StorageFailedError(_STORAGE_ERROR) from error

    def initialize_collection(self) -> None:
        """Explicitly create or verify the configured cosine collection."""
        try:
            collection = self._client.get_or_create_collection(
                name=self._config.collection,
                configuration={"hnsw": {"space": "cosine"}},
                embedding_function=None,
            )
            self._validate_collection_configuration(collection)
        except (ChromaError, OSError, RuntimeError, ValueError) as error:
            raise StorageFailedError(_STORAGE_ERROR) from error

    def add_chunks(
        self,
        chunks: Sequence[CodeChunk],
        embeddings: NDArray[np.generic],
    ) -> None:
        """Persist source-only chunks with caller-generated embeddings."""
        validated_chunks = self._validate_chunks(chunks)
        vectors = self._validate_embeddings(embeddings, expected_rows=len(validated_chunks))
        self.initialize_collection()
        if not validated_chunks:
            return
        metadatas: list[Metadata] = [self._chunk_metadata(chunk) for chunk in validated_chunks]
        try:
            self._get_collection().add(
                ids=[chunk.id for chunk in validated_chunks],
                embeddings=vectors.tolist(),
                documents=[chunk.text for chunk in validated_chunks],
                metadatas=metadatas,
            )
        except (ChromaError, OSError, RuntimeError, ValueError) as error:
            raise StorageFailedError(_STORAGE_ERROR) from error

    def query(
        self,
        query_embedding: NDArray[np.generic],
        *,
        limit: int,
        language: str | None = None,
    ) -> list[StoredChunkMatch]:
        """Return aligned Chroma matches without requesting stored embeddings."""
        vector = self._validate_query_embedding(query_embedding)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            raise ValueError(_INPUT_ERROR)
        where: Where | None = None
        if language is not None:
            normalized = normalize_language(language)
            where = cast(Where, {"language": {"$eq": normalized}})
        try:
            result = self._get_collection().query(
                query_embeddings=vector.tolist(),
                n_results=limit,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
            return self._parse_query_result(result)
        except StorageFailedError:
            raise
        except (ChromaError, OSError, RuntimeError, ValueError, ValidationError) as error:
            raise StorageFailedError(_STORAGE_ERROR) from error

    def count(self) -> int:
        """Return the number of stored chunks without creating a collection."""
        try:
            return self._get_collection().count()
        except StorageFailedError:
            raise
        except (ChromaError, OSError, RuntimeError, ValueError) as error:
            raise StorageFailedError(_STORAGE_ERROR) from error

    def delete_by_file(self, file: str) -> None:
        """Delete chunks for one exact project-relative file."""
        validated_file = _validate_public_path(file)
        try:
            self._get_collection().delete(where=cast(Where, {"file": {"$eq": validated_file}}))
        except StorageFailedError:
            raise
        except (ChromaError, OSError, RuntimeError, ValueError) as error:
            raise StorageFailedError(_STORAGE_ERROR) from error

    def reset_collection(self, *, remove_metadata: bool = False) -> None:
        """Reset only the configured collection and optionally known metadata files."""
        try:
            self._client.delete_collection(self._config.collection)
        except NotFoundError:
            pass
        except (ChromaError, OSError, RuntimeError, ValueError) as error:
            raise StorageFailedError(_STORAGE_ERROR) from error
        self.initialize_collection()
        if remove_metadata:
            try:
                remove_metadata_file(self._runtime_root, _SYMBOLS_FILE)
                remove_metadata_file(self._runtime_root, _INDEX_METADATA_FILE)
            except (InvalidPathError, OSError, RuntimeError, ValueError) as error:
                raise StorageFailedError(_STORAGE_ERROR) from error

    def write_symbols(self, symbols: Sequence[Symbol]) -> None:
        """Atomically persist validated immutable parser symbols."""
        if isinstance(symbols, (str, bytes)) or not isinstance(symbols, Sequence):
            raise ValueError(_INPUT_ERROR)
        if any(not isinstance(symbol, Symbol) for symbol in symbols):
            raise ValueError(_INPUT_ERROR)
        payload = [symbol.model_dump(mode="json") for symbol in symbols]
        try:
            atomic_write_metadata_json(self._runtime_root, _SYMBOLS_FILE, payload)
        except (
            InvalidPathError,
            OSError,
            RuntimeError,
            TypeError,
            UnicodeError,
            ValueError,
        ) as error:
            raise StorageFailedError(_STORAGE_ERROR) from error

    def read_symbols(self) -> list[Symbol]:
        """Read and validate every symbol from atomic local metadata."""
        try:
            payload = read_metadata_json(self._runtime_root, _SYMBOLS_FILE)
            if not isinstance(payload, list):
                raise ValueError(_INPUT_ERROR)
            return [Symbol.model_validate(item) for item in payload]
        except (
            InvalidPathError,
            OSError,
            RuntimeError,
            TypeError,
            UnicodeError,
            ValueError,
            ValidationError,
        ) as error:
            raise StorageFailedError(_STORAGE_ERROR) from error

    def write_index_metadata(self, metadata: IndexMetadata) -> None:
        """Atomically persist validated internal index metadata."""
        if not isinstance(metadata, IndexMetadata):
            raise ValueError(_INPUT_ERROR)
        try:
            atomic_write_metadata_json(
                self._runtime_root,
                _INDEX_METADATA_FILE,
                metadata.model_dump(mode="json"),
            )
        except (
            InvalidPathError,
            OSError,
            RuntimeError,
            TypeError,
            UnicodeError,
            ValueError,
        ) as error:
            raise StorageFailedError(_STORAGE_ERROR) from error

    def read_index_metadata(self) -> IndexMetadata:
        """Read and validate atomic internal index metadata."""
        try:
            payload = read_metadata_json(self._runtime_root, _INDEX_METADATA_FILE)
            return IndexMetadata.model_validate(payload)
        except (
            InvalidPathError,
            OSError,
            RuntimeError,
            TypeError,
            UnicodeError,
            ValueError,
            ValidationError,
        ) as error:
            raise StorageFailedError(_STORAGE_ERROR) from error

    def _get_collection(self) -> Collection:
        try:
            collection = self._client.get_collection(
                name=self._config.collection,
                embedding_function=None,
            )
            self._validate_collection_configuration(collection)
            return collection
        except NotFoundError as error:
            raise StorageFailedError(
                _MISSING_COLLECTION_ERROR,
                suggestion="Initialize or rebuild the local CodeScope index and retry.",
            ) from error

    @staticmethod
    def _validate_collection_configuration(collection: Collection) -> None:
        configuration = collection.configuration
        hnsw = configuration.get("hnsw")
        if (
            not isinstance(hnsw, Mapping)
            or hnsw.get("space") != "cosine"
            or configuration.get("embedding_function") is not None
        ):
            raise ValueError(_INPUT_ERROR)

    @staticmethod
    def _validate_chunks(chunks: Sequence[CodeChunk]) -> list[CodeChunk]:
        if isinstance(chunks, (str, bytes)) or not isinstance(chunks, Sequence):
            raise ValueError(_INPUT_ERROR)
        result = list(chunks)
        if any(not isinstance(chunk, CodeChunk) for chunk in result):
            raise ValueError(_INPUT_ERROR)
        identifiers = [chunk.id for chunk in result]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError(_INPUT_ERROR)
        return result

    @staticmethod
    def _validate_embeddings(
        embeddings: NDArray[np.generic],
        *,
        expected_rows: int,
    ) -> NDArray[np.float32]:
        if not isinstance(embeddings, np.ndarray) or embeddings.ndim != 2:
            raise ValueError(_INPUT_ERROR)
        if embeddings.shape[0] != expected_rows or embeddings.shape[1] <= 0:
            raise ValueError(_INPUT_ERROR)
        if not np.issubdtype(embeddings.dtype, np.number):
            raise ValueError(_INPUT_ERROR)
        try:
            result = embeddings.astype(np.float32, copy=False)
        except (TypeError, ValueError) as error:
            raise ValueError(_INPUT_ERROR) from error
        if not np.isfinite(result).all():
            raise ValueError(_INPUT_ERROR)
        return result

    @classmethod
    def _validate_query_embedding(
        cls,
        embedding: NDArray[np.generic],
    ) -> NDArray[np.float32]:
        if not isinstance(embedding, np.ndarray):
            raise ValueError(_INPUT_ERROR)
        if embedding.ndim == 1:
            embedding = embedding.reshape(1, -1)
        if embedding.ndim != 2 or embedding.shape[0] != 1:
            raise ValueError(_INPUT_ERROR)
        return cls._validate_embeddings(embedding, expected_rows=1)

    @staticmethod
    def _chunk_metadata(chunk: CodeChunk) -> Metadata:
        return {
            "file": chunk.file,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
            "language": chunk.language,
            "symbol_name": chunk.symbol_name or "",
            "qualified_name": chunk.qualified_name or "",
            "chunk_index": chunk.chunk_index,
            "content_hash": chunk.content_hash,
        }

    @staticmethod
    def _parse_query_result(result: Mapping[str, object]) -> list[StoredChunkMatch]:
        identifiers = ChromaStorage._single_result_row(result.get("ids"))
        documents = ChromaStorage._single_result_row(result.get("documents"))
        metadatas = ChromaStorage._single_result_row(result.get("metadatas"))
        distances = ChromaStorage._single_result_row(result.get("distances"))
        if not (len(identifiers) == len(documents) == len(metadatas) == len(distances)):
            raise ValueError(_INPUT_ERROR)
        matches: list[StoredChunkMatch] = []
        for identifier, document, metadata, distance in zip(
            identifiers,
            documents,
            metadatas,
            distances,
            strict=True,
        ):
            if (
                not isinstance(identifier, str)
                or not isinstance(document, str)
                or not isinstance(metadata, Mapping)
                or not isinstance(distance, (int, float))
                or isinstance(distance, bool)
                or not math.isfinite(distance)
            ):
                raise ValueError(_INPUT_ERROR)
            symbol_name = metadata.get("symbol_name")
            qualified_name = metadata.get("qualified_name")
            chunk = CodeChunk.model_validate(
                {
                    "id": identifier,
                    "text": document,
                    "file": metadata.get("file"),
                    "start_line": metadata.get("start_line"),
                    "end_line": metadata.get("end_line"),
                    "language": metadata.get("language"),
                    "symbol_name": symbol_name or None,
                    "qualified_name": qualified_name or None,
                    "chunk_index": metadata.get("chunk_index"),
                    "content_hash": metadata.get("content_hash"),
                }
            )
            matches.append(StoredChunkMatch(**chunk.model_dump(), distance=float(distance)))
        return matches

    @staticmethod
    def _single_result_row(value: object) -> Sequence[object]:
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != 1:
            raise ValueError(_INPUT_ERROR)
        row = value[0]
        if isinstance(row, (str, bytes)) or not isinstance(row, Sequence):
            raise ValueError(_INPUT_ERROR)
        return cast(Sequence[object], row)
