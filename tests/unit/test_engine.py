"""Unit tests for read-only semantic and symbol query orchestration."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, NoReturn, cast

import numpy as np
import pytest
from pydantic import ValidationError

import codescope.engine as engine_module
from codescope.config import (
    AppConfig,
    EmbeddingsConfig,
    IndexConfig,
    SearchConfig,
    ServerConfig,
    StorageConfig,
)
from codescope.engine import QueryEngine
from codescope.exceptions import (
    ErrorCode,
    IndexNotFoundError,
    InvalidLanguageError,
    InvalidLimitError,
    InvalidQueryError,
    QueryFailedError,
    StorageFailedError,
)
from codescope.models import IndexStatus, SearchResult, Symbol
from codescope.storage import StoredChunkMatch


def _config(root: Path, runtime: Path) -> AppConfig:
    root.mkdir(parents=True, exist_ok=True)
    return AppConfig(
        server=ServerConfig(name="codescope", transport="stdio"),
        index=IndexConfig(
            root=root,
            languages=("python",),
            include_extensions=(".py", ".pyi"),
            exclude=(".git", ".codescope", ".venv", "__pycache__"),
            max_file_size_kb=500,
            max_chunk_wordpieces=220,
            chunk_overlap_wordpieces=30,
            follow_symlinks=False,
        ),
        embeddings=EmbeddingsConfig(
            model="sentence-transformers/all-MiniLM-L6-v2",
            batch_size=32,
            device="cpu",
            normalize=True,
        ),
        storage=StorageConfig(path=runtime, collection="codescope_chunks"),
        search=SearchConfig(default_limit=5, maximum_limit=20, minimum_query_characters=2),
    )


def _status(*, symbols: int = 1, chunks: int = 1) -> IndexStatus:
    return IndexStatus(
        index_exists=True,
        index_root=".",
        total_files=1,
        total_chunks=chunks,
        total_symbols=symbols,
        languages={"python": 1},
        last_indexed="2026-07-16T12:00:00Z",
        index_size_bytes=1024,
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    )


def _symbol(
    name: str = "validate_email",
    *,
    qualified_name: str | None = None,
    kind: str = "function",
    file: str = "validators.py",
    start_line: int = 6,
    end_line: int = 9,
) -> Symbol:
    return Symbol(
        name=name,
        kind=kind,
        file=file,
        start_line=start_line,
        end_line=end_line,
        signature=f"def {name}() -> bool:",
        qualified_name=qualified_name or name,
        docstring="Validate input.",
        language="python",
    )


def _match(
    identifier: str,
    *,
    distance: float = 0.1,
    file: str = "validators.py",
    start_line: int = 6,
    end_line: int = 9,
    text: str = "def validate_email(email: str) -> bool:\n    return '@' in email\n",
    symbol_name: str | None = "validate_email",
    qualified_name: str | None = "validate_email",
) -> StoredChunkMatch:
    return StoredChunkMatch(
        id=identifier,
        text=text,
        file=file,
        start_line=start_line,
        end_line=end_line,
        language="python",
        symbol_name=symbol_name,
        qualified_name=qualified_name,
        chunk_index=0,
        content_hash=identifier[0] * 64,
        distance=distance,
    )


class FakeEmbedder:
    embedding_dimension = 3

    def __init__(self, output: object | None = None, *, fail: bool = False) -> None:
        self.output = output
        self.fail = fail
        self.calls: list[tuple[str, ...]] = []

    def encode(self, texts: Sequence[str]) -> Any:
        self.calls.append(tuple(texts))
        if self.fail:
            raise RuntimeError("private model failure")
        if self.output is not None:
            return self.output
        return np.array([[1.0, 0.0, 0.0]], dtype=np.float32)


class FakeStorage:
    def __init__(
        self,
        *,
        matches: Sequence[StoredChunkMatch] = (),
        symbols: Sequence[Symbol] = (),
        query_error: Exception | None = None,
        symbol_error: Exception | None = None,
    ) -> None:
        self.matches: object = list(matches)
        self.symbols = list(symbols)
        self.query_error = query_error
        self.symbol_error = symbol_error
        self.query_calls: list[tuple[np.ndarray[Any, Any], int, str | None]] = []
        self.read_symbol_calls = 0
        self.close_calls = 0

    def query(
        self,
        query_embedding: np.ndarray[Any, Any],
        *,
        limit: int,
        language: str | None = None,
    ) -> list[StoredChunkMatch]:
        self.query_calls.append((query_embedding.copy(), limit, language))
        if self.query_error is not None:
            raise self.query_error
        return cast(list[StoredChunkMatch], self.matches)

    def read_symbols(self) -> list[Symbol]:
        self.read_symbol_calls += 1
        if self.symbol_error is not None:
            raise self.symbol_error
        return list(self.symbols)

    def close(self) -> None:
        self.close_calls += 1


class FakeStorageFactory:
    def __init__(self, storage: FakeStorage, *, error: Exception | None = None) -> None:
        self.storage = storage
        self.error = error
        self.calls: list[tuple[StorageConfig, bool]] = []

    def __call__(self, config: StorageConfig, *, create: bool = True) -> FakeStorage:
        self.calls.append((config, create))
        if self.error is not None:
            raise self.error
        return self.storage


def _engine(
    tmp_path: Path,
    *,
    embedder: FakeEmbedder | None = None,
    storage: FakeStorage | None = None,
    status: IndexStatus | None = None,
    status_provider: Any | None = None,
) -> tuple[QueryEngine, FakeEmbedder, FakeStorage, FakeStorageFactory]:
    config = _config(tmp_path / "repo", tmp_path / "runtime")
    fake_embedder = embedder or FakeEmbedder()
    fake_storage = storage or FakeStorage(matches=[_match("a" * 64)], symbols=[_symbol()])
    factory = FakeStorageFactory(fake_storage)
    provider = status_provider or (lambda: status or _status())
    engine = QueryEngine(
        config,
        embedder=fake_embedder,
        storage_factory=factory,
        status_provider=provider,
    )
    return engine, fake_embedder, fake_storage, factory


def test_constructor_is_lazy_and_opens_no_storage_or_model(tmp_path: Path) -> None:
    # Arrange
    config = _config(tmp_path / "repo", tmp_path / "runtime")

    def fail_status() -> NoReturn:
        raise AssertionError("status loaded")

    factory = FakeStorageFactory(FakeStorage(), error=AssertionError("storage opened"))

    # Act
    engine = QueryEngine(config, storage_factory=factory, status_provider=fail_status)

    # Assert
    assert isinstance(engine, QueryEngine)
    assert factory.calls == []
    assert not config.storage.path.exists()


def test_missing_index_query_is_actionable_and_creates_no_runtime(tmp_path: Path) -> None:
    # Arrange
    config = _config(tmp_path / "repo", tmp_path / "runtime")
    engine = QueryEngine(config)

    # Act
    with pytest.raises(IndexNotFoundError) as error_info:
        engine.search_code("email validation")

    # Assert
    assert error_info.value.code is ErrorCode.INDEX_NOT_FOUND
    assert error_info.value.suggestion == "Build the index before running a query."
    assert not config.storage.path.exists()
    assert list(tmp_path.glob("runtime.build-*")) == []
    assert list(tmp_path.glob("runtime.backup-*")) == []


def test_get_index_status_returns_authoritative_immutable_status_without_model(
    tmp_path: Path,
) -> None:
    # Arrange
    expected = _status()
    engine, embedder, _, factory = _engine(tmp_path, status=expected)

    # Act
    result = engine.get_index_status()

    # Assert
    assert result is expected
    assert result.index_root == "."
    assert embedder.calls == []
    assert factory.calls == []
    with pytest.raises(ValidationError):
        result.total_files = 3  # type: ignore[misc]


def test_default_status_and_symbol_paths_never_instantiate_embedder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    config = _config(tmp_path / "repo", tmp_path / "runtime")
    storage = FakeStorage(symbols=[_symbol()])
    factory = FakeStorageFactory(storage)

    def reject_embedder(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("embedder instantiated")

    monkeypatch.setattr(engine_module, "LocalEmbedder", reject_embedder)
    engine = QueryEngine(
        config,
        storage_factory=factory,
        status_provider=lambda: _status(),
    )

    # Act
    status = engine.get_index_status()
    symbols = engine.find_symbol("validate_email")

    # Assert
    assert status.index_exists is True
    assert symbols[0].name == "validate_email"


def test_false_index_status_is_treated_as_missing(tmp_path: Path) -> None:
    # Arrange
    missing = _status().model_copy(update={"index_exists": False})
    engine, _, _, _ = _engine(tmp_path, status=missing)

    # Act and Assert
    with pytest.raises(IndexNotFoundError):
        engine.get_index_status()


def test_semantic_search_normalizes_query_and_passes_language_and_limit(tmp_path: Path) -> None:
    # Arrange
    engine, embedder, storage, factory = _engine(tmp_path)

    # Act
    results = engine.search_code("  email validation  ", language=" PYTHON ", limit=1)

    # Assert
    assert embedder.calls == [("email validation",)]
    assert len(storage.query_calls) == 1
    assert storage.query_calls[0][1:] == (1, "python")
    assert factory.calls[0][1] is False
    assert storage.close_calls == 1
    assert results[0].file == "validators.py"
    assert results[0].start_line == 6
    assert results[0].end_line == 9


@pytest.mark.parametrize(
    ("distance", "expected"),
    [(-2.0, 1.0), (0.0, 1.0), (0.25, 0.75), (1.0, 0.0), (3.0, 0.0)],
)
def test_semantic_relevance_is_one_minus_cosine_distance_and_clamped(
    tmp_path: Path,
    distance: float,
    expected: float,
) -> None:
    # Arrange
    storage = FakeStorage(matches=[_match("a" * 64, distance=distance)])
    engine, _, _, _ = _engine(tmp_path, storage=storage)

    # Act
    result = engine.search_code("email validation", limit=1)

    # Assert
    assert result[0].relevance_score == expected


def test_semantic_ties_use_deterministic_traceable_order(tmp_path: Path) -> None:
    # Arrange
    matches = [
        _match("d" * 64, file="z.py", start_line=1, end_line=2),
        _match("c" * 64, file="a.py", start_line=8, end_line=9),
        _match("b" * 64, file="a.py", start_line=2, end_line=3, qualified_name="zeta"),
        _match("a" * 64, file="a.py", start_line=2, end_line=3, qualified_name="alpha"),
    ]
    storage = FakeStorage(matches=list(reversed(matches)))
    engine, _, _, _ = _engine(tmp_path, storage=storage, status=_status(chunks=4))

    # Act
    first = engine.search_code("email validation", limit=4)
    second = engine.search_code("email validation", limit=4)

    # Assert
    expected = ["alpha", "zeta", "validate_email", "validate_email"]
    assert [item.qualified_name for item in first] == expected
    assert first == second


def test_semantic_results_are_source_only_bounded_and_immutable(tmp_path: Path) -> None:
    # Arrange
    stored = "x" * 10_000
    storage = FakeStorage(matches=[_match("a" * 64, text=stored)])
    engine, _, _, _ = _engine(tmp_path, storage=storage)

    # Act
    result = engine.search_code("email validation", limit=1)[0]

    # Assert
    assert result.snippet == stored[:8192]
    assert not hasattr(result, "embedding")
    with pytest.raises(ValidationError):
        result.snippet = "changed"  # type: ignore[misc]


def test_semantic_query_never_reads_repository_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    engine, _, _, _ = _engine(tmp_path)

    def reject_read(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("source read")

    monkeypatch.setattr(Path, "read_text", reject_read)
    monkeypatch.setattr(Path, "read_bytes", reject_read)

    # Act and Assert
    assert engine.search_code("email validation", limit=1)[0].symbol == "validate_email"


@pytest.mark.parametrize("query", ["", " ", "x", 42, None, "x" * 16_385])
def test_invalid_semantic_query_raises_typed_error_without_echo(
    tmp_path: Path,
    query: object,
) -> None:
    # Arrange
    engine, _, _, _ = _engine(tmp_path)

    # Act
    with pytest.raises(InvalidQueryError) as error_info:
        engine.search_code(query)  # type: ignore[arg-type]

    # Assert
    assert error_info.value.code is ErrorCode.INVALID_QUERY
    if str(query).strip():
        assert str(query) not in str(error_info.value)


@pytest.mark.parametrize("limit", [0, -1, 21, True, 1.5, "3"])
def test_invalid_semantic_limit_raises_typed_error(tmp_path: Path, limit: object) -> None:
    # Arrange
    engine, _, _, _ = _engine(tmp_path)

    # Act and Assert
    with pytest.raises(InvalidLimitError) as error_info:
        engine.search_code("email validation", limit=limit)  # type: ignore[arg-type]
    assert error_info.value.code is ErrorCode.INVALID_LIMIT


@pytest.mark.parametrize("limit", [0, -1, 21, True, 1.5, "3"])
def test_invalid_symbol_limit_raises_typed_error(tmp_path: Path, limit: object) -> None:
    # Arrange
    engine, _, _, _ = _engine(tmp_path)

    # Act and Assert
    with pytest.raises(InvalidLimitError):
        engine.find_symbol("validate_email", limit=limit)  # type: ignore[arg-type]


@pytest.mark.parametrize("language", ["typescript", "", 42])
def test_invalid_semantic_language_raises_typed_error(tmp_path: Path, language: object) -> None:
    # Arrange
    engine, _, _, _ = _engine(tmp_path)

    # Act and Assert
    with pytest.raises(InvalidLanguageError):
        engine.search_code("email validation", language=language)  # type: ignore[arg-type]


def test_symbol_ranking_uses_all_required_groups(tmp_path: Path) -> None:
    # Arrange
    symbols = [
        _symbol("revalidate"),
        _symbol("validate_email"),
        _symbol("qualified", qualified_name="validate"),
        _symbol("Validate"),
        _symbol("validate"),
    ]
    storage = FakeStorage(symbols=list(reversed(symbols)))
    engine, embedder, _, _ = _engine(
        tmp_path,
        storage=storage,
        status=_status(symbols=len(symbols)),
    )

    # Act
    results = engine.find_symbol("validate")

    # Assert
    assert [result.name for result in results] == [
        "validate",
        "Validate",
        "qualified",
        "validate_email",
        "revalidate",
    ]
    assert embedder.calls == []


def test_symbol_kind_filter_is_applied_before_limit(tmp_path: Path) -> None:
    # Arrange
    symbols = [
        _symbol("validate", kind="class"),
        _symbol("validate", kind="function", file="b.py"),
        _symbol("validate_more", kind="function", file="a.py"),
    ]
    storage = FakeStorage(symbols=symbols)
    engine, _, _, _ = _engine(tmp_path, storage=storage, status=_status(symbols=3))

    # Act
    result = engine.find_symbol("validate", kind=" FUNCTION ", limit=1)

    # Assert
    assert len(result) == 1
    assert result[0].kind == "function"


@pytest.mark.parametrize("kind", ["module", "", 7])
def test_unsupported_symbol_kind_is_rejected_safely(tmp_path: Path, kind: object) -> None:
    # Arrange
    engine, _, _, _ = _engine(tmp_path)

    # Act and Assert
    with pytest.raises(InvalidQueryError) as error_info:
        engine.find_symbol("validate_email", kind=kind)  # type: ignore[arg-type]
    assert "validate_email" not in str(error_info.value)


@pytest.mark.parametrize("name", ["", "   ", 9, "x" * 1_025])
def test_invalid_symbol_name_is_rejected_safely(tmp_path: Path, name: object) -> None:
    # Arrange
    engine, _, _, _ = _engine(tmp_path)

    # Act and Assert
    with pytest.raises(InvalidQueryError):
        engine.find_symbol(name)  # type: ignore[arg-type]


def test_exact_symbol_lookup_preserves_path_lines_signature_and_docstring(tmp_path: Path) -> None:
    # Arrange
    symbol = _symbol(file="validators.py", start_line=6, end_line=9)
    storage = FakeStorage(symbols=[symbol])
    engine, _, _, factory = _engine(tmp_path, storage=storage)

    # Act
    result = engine.find_symbol("validate_email")

    # Assert
    assert len(result) == 1
    assert result[0].file == "validators.py"
    assert (result[0].start_line, result[0].end_line) == (6, 9)
    assert result[0].signature == symbol.signature
    assert result[0].docstring == symbol.docstring
    assert factory.calls[0][1] is False


def test_symbol_results_are_deduplicated_limited_and_deterministic(tmp_path: Path) -> None:
    # Arrange
    first = _symbol("validate_one", file="b.py")
    second = _symbol("validate_two", file="a.py")
    storage = FakeStorage(symbols=[first, first, second])
    engine, _, _, _ = _engine(tmp_path, storage=storage, status=_status(symbols=3))

    # Act
    results = engine.find_symbol("validate", limit=1)

    # Assert
    assert [result.name for result in results] == ["validate_one"]


def test_symbol_lookup_detects_index_replacement_count_mismatch(tmp_path: Path) -> None:
    # Arrange
    storage = FakeStorage(symbols=[])
    engine, _, _, _ = _engine(tmp_path, storage=storage, status=_status(symbols=1))

    # Act and Assert
    with pytest.raises(IndexNotFoundError):
        engine.find_symbol("validate_email")


def test_symbol_lookup_never_loads_model_or_reads_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    engine, embedder, storage, _ = _engine(tmp_path)

    def reject_read(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("source read")

    monkeypatch.setattr(Path, "read_text", reject_read)
    monkeypatch.setattr(Path, "read_bytes", reject_read)

    # Act
    result = engine.find_symbol("validate_email")

    # Assert
    assert result[0].name == "validate_email"
    assert embedder.calls == []
    assert storage.read_symbol_calls == 1


def test_find_similar_reuses_semantic_path_with_default_limit_and_language(tmp_path: Path) -> None:
    # Arrange
    engine, embedder, storage, _ = _engine(tmp_path)

    # Act
    result = engine.find_similar("  def planned(value): return value  ", language="python")

    # Assert
    assert result and isinstance(result[0], SearchResult)
    assert embedder.calls == [("def planned(value): return value",)]
    assert storage.query_calls[0][1:] == (3, "python")
    assert "does not prove" in (QueryEngine.find_similar.__doc__ or "")
    assert not hasattr(result[0], "equivalent")


def test_storage_failure_is_preserved_for_semantic_search(tmp_path: Path) -> None:
    # Arrange
    expected = StorageFailedError("Safe storage failure.")
    storage = FakeStorage(query_error=expected)
    engine, _, _, _ = _engine(tmp_path, storage=storage)

    # Act
    with pytest.raises(StorageFailedError) as error_info:
        engine.search_code("email validation")

    # Assert
    assert error_info.value is expected


def test_storage_failure_is_preserved_for_symbol_lookup(tmp_path: Path) -> None:
    # Arrange
    expected = StorageFailedError("Safe storage failure.")
    storage = FakeStorage(symbol_error=expected)
    engine, _, _, _ = _engine(tmp_path, storage=storage)

    # Act and Assert
    with pytest.raises(StorageFailedError) as error_info:
        engine.find_symbol("validate_email")
    assert error_info.value is expected


def test_missing_collection_status_failure_remains_index_not_found(tmp_path: Path) -> None:
    # Arrange
    expected = IndexNotFoundError("No complete usable CodeScope index exists.")

    def missing() -> NoReturn:
        raise expected

    engine, _, _, factory = _engine(tmp_path, status_provider=missing)

    # Act and Assert
    with pytest.raises(IndexNotFoundError) as error_info:
        engine.search_code("email validation")
    assert error_info.value is expected
    assert factory.calls == []


def test_known_status_storage_failure_is_preserved(tmp_path: Path) -> None:
    # Arrange
    expected = StorageFailedError("Safe status storage failure.")

    def fail_status() -> NoReturn:
        raise expected

    engine, _, _, _ = _engine(tmp_path, status_provider=fail_status)

    # Act and Assert
    with pytest.raises(StorageFailedError) as error_info:
        engine.get_index_status()
    assert error_info.value is expected


def test_unexpected_embedder_failure_becomes_safe_query_failure(tmp_path: Path) -> None:
    # Arrange
    raw = "PRIVATE_QUERY_MARKER"
    embedder = FakeEmbedder(fail=True)
    engine, _, _, _ = _engine(tmp_path, embedder=embedder)

    # Act
    with pytest.raises(QueryFailedError) as error_info:
        engine.search_code(raw)

    # Assert
    assert error_info.value.code is ErrorCode.QUERY_FAILED
    assert raw not in str(error_info.value)
    assert "private model failure" not in str(error_info.value)


@pytest.mark.parametrize(
    "output",
    [
        [[1.0, 0.0, 0.0]],
        np.ones((2, 3), dtype=np.float32),
        np.ones((1, 2), dtype=np.float32),
        np.array([[np.nan, 0.0, 0.0]], dtype=np.float32),
        np.array([[np.inf, 0.0, 0.0]], dtype=np.float32),
        np.array([[True, False, True]], dtype=np.bool_),
    ],
)
def test_invalid_embedder_output_becomes_query_failure(tmp_path: Path, output: object) -> None:
    # Arrange
    engine, _, _, _ = _engine(tmp_path, embedder=FakeEmbedder(output=output))

    # Act and Assert
    with pytest.raises(QueryFailedError):
        engine.search_code("email validation")


def test_malformed_storage_result_becomes_safe_query_failure(tmp_path: Path) -> None:
    # Arrange
    secret = "PRIVATE_STORED_SOURCE"
    storage = FakeStorage()
    storage.matches = [{"text": secret, "file": "/private/path.py"}]
    engine, _, _, _ = _engine(tmp_path, storage=storage)

    # Act
    with pytest.raises(QueryFailedError) as error_info:
        engine.search_code("email validation")

    # Assert
    message = str(error_info.value)
    assert secret not in message
    assert "/private/path.py" not in message


def test_storage_returning_more_than_requested_is_rejected(tmp_path: Path) -> None:
    # Arrange
    storage = FakeStorage(matches=[_match("a" * 64), _match("b" * 64)])
    engine, _, _, _ = _engine(tmp_path, storage=storage, status=_status(chunks=2))

    # Act and Assert
    with pytest.raises(QueryFailedError):
        engine.search_code("email validation", limit=1)


def test_unexpected_status_failure_is_safely_chained(tmp_path: Path) -> None:
    # Arrange
    def fail_status() -> NoReturn:
        raise RuntimeError("private runtime path /secret/repo")

    engine, _, _, _ = _engine(tmp_path, status_provider=fail_status)

    # Act
    with pytest.raises(QueryFailedError) as error_info:
        engine.get_index_status()

    # Assert
    assert "/secret/repo" not in str(error_info.value)
    assert isinstance(error_info.value.__cause__, RuntimeError)
