"""Unit tests for persistent Chroma storage and atomic metadata."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
from pydantic import ValidationError

from codescope.config import StorageConfig
from codescope.exceptions import ErrorCode, InvalidPathError, StorageFailedError
from codescope.models import CodeChunk, Symbol
from codescope.storage import ChromaStorage, IndexMetadata
from codescope.utils.json_io import (
    INDEX_METADATA_MAX_BYTES,
    SYMBOLS_METADATA_MAX_BYTES,
    atomic_write_metadata_json,
    read_metadata_json,
)


def _config(path: Path) -> StorageConfig:
    return StorageConfig(path=path, collection="codescope_chunks")


def _chunk(
    identifier: str,
    *,
    file: str = "src/example.py",
    text: str = "def example():\n    return True\n",
    symbol_name: str | None = "example",
    qualified_name: str | None = "example",
) -> CodeChunk:
    return CodeChunk(
        id=identifier,
        text=text,
        file=file,
        start_line=1,
        end_line=2,
        language="python",
        symbol_name=symbol_name,
        qualified_name=qualified_name,
        chunk_index=0,
        content_hash=(identifier[0] if identifier else "0") * 64,
    )


def _symbol() -> Symbol:
    return Symbol(
        name="example",
        kind="function",
        file="src/example.py",
        start_line=1,
        end_line=2,
        signature="def example() -> bool:",
        qualified_name="example",
        docstring=None,
        language="python",
    )


def _metadata() -> IndexMetadata:
    return IndexMetadata(
        codescope_version="0.1.0",
        index_root=".",
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        timestamp="2026-07-15T12:00:00Z",
        file_count=1,
        symbol_count=1,
        chunk_count=1,
        language_counts={"python": 1},
        configuration_fingerprint="a" * 64,
    )


def test_storage_initializes_only_runtime_and_chroma_directories(tmp_path: Path) -> None:
    # Arrange
    runtime = tmp_path / "nested" / ".codescope"

    # Act
    storage = ChromaStorage(_config(runtime))

    # Assert
    assert runtime.is_dir()
    assert (runtime / "chroma").is_dir()
    assert storage._settings.anonymized_telemetry is False
    assert storage._settings.allow_reset is False


def test_open_existing_mode_does_not_create_missing_runtime(tmp_path: Path) -> None:
    # Arrange
    runtime = tmp_path / ".codescope"

    # Act and Assert
    with pytest.raises(StorageFailedError):
        ChromaStorage(_config(runtime), create=False)
    assert not runtime.exists()


def test_close_is_idempotent_and_releases_runtime_for_sibling_rename(tmp_path: Path) -> None:
    # Arrange
    runtime = tmp_path / ".codescope"
    replacement = tmp_path / ".codescope.backup-test"
    storage = ChromaStorage(_config(runtime))
    storage.initialize_collection()

    # Act
    storage.close()
    storage.close()
    os.replace(runtime, replacement)

    # Assert
    assert replacement.is_dir()
    assert not runtime.exists()


def test_storage_rejects_symlinked_runtime_even_if_config_validation_is_bypassed(
    tmp_path: Path,
) -> None:
    # Arrange
    external = tmp_path / "external"
    external.mkdir()
    link = tmp_path / "runtime-link"
    try:
        link.symlink_to(external, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlink creation unavailable on this operating system: {error}")
    unsafe = StorageConfig.model_construct(path=link, collection="codescope_chunks")

    # Act and Assert
    with pytest.raises(StorageFailedError) as error_info:
        ChromaStorage(unsafe)
    assert str(tmp_path) not in str(error_info.value)


def test_storage_config_rejects_runtime_symlink_before_resolution(tmp_path: Path) -> None:
    # Arrange
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlink creation unavailable on this operating system: {error}")

    # Act and Assert
    with pytest.raises(ValidationError):
        _config(link)


def test_collection_initialization_is_explicit_cosine_without_embedding_function(
    tmp_path: Path,
) -> None:
    # Arrange
    storage = ChromaStorage(_config(tmp_path / ".codescope"))

    # Act
    storage.initialize_collection()
    collection = storage._client.get_collection("codescope_chunks", embedding_function=None)

    # Assert
    assert collection.configuration["hnsw"]["space"] == "cosine"
    assert collection.configuration["embedding_function"] is None


def test_add_count_query_and_metadata_round_trip_with_optional_names(tmp_path: Path) -> None:
    # Arrange
    storage = ChromaStorage(_config(tmp_path / ".codescope"))
    chunks = [
        _chunk("a" * 64),
        _chunk(
            "b" * 64,
            file="src/module.py",
            text="VALUE = 1\n",
            symbol_name=None,
            qualified_name=None,
        ),
    ]
    vectors = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)

    # Act
    storage.add_chunks(chunks, vectors)
    matches = storage.query(np.array([1.0, 0.0], dtype=np.float32), limit=2)

    # Assert
    assert storage.count() == 2
    assert [match.id for match in matches] == ["a" * 64, "b" * 64]
    assert matches[0].text == chunks[0].text
    assert matches[0].file == "src/example.py"
    assert matches[0].symbol_name == "example"
    assert matches[1].symbol_name is None
    assert matches[1].qualified_name is None
    assert not hasattr(matches[0], "embedding")


def test_persistence_survives_a_second_storage_instance(tmp_path: Path) -> None:
    # Arrange
    config = _config(tmp_path / ".codescope")
    first = ChromaStorage(config)
    first.add_chunks([_chunk("a" * 64)], np.array([[1.0, 0.0]], dtype=np.float32))

    # Act
    second = ChromaStorage(config)

    # Assert
    assert second.count() == 1
    assert second.query(np.array([[1.0, 0.0]], dtype=np.float32), limit=1)[0].id == "a" * 64


def test_language_filter_uses_installed_chroma_where_syntax(tmp_path: Path) -> None:
    # Arrange
    storage = ChromaStorage(_config(tmp_path / ".codescope"))
    storage.add_chunks([_chunk("a" * 64)], np.array([[1.0, 0.0]], dtype=np.float32))

    # Act
    matches = storage.query(
        np.array([1.0, 0.0], dtype=np.float32),
        limit=1,
        language=" PYTHON ",
    )

    # Assert
    assert len(matches) == 1
    assert matches[0].language == "python"


@pytest.mark.parametrize(
    "embeddings",
    [
        np.array([1.0, 0.0], dtype=np.float32),
        np.ones((2, 2), dtype=np.float32),
        np.empty((1, 0), dtype=np.float32),
        np.array([[np.nan, 0.0]], dtype=np.float32),
        np.array([[np.inf, 0.0]], dtype=np.float32),
        np.array([[True, False]], dtype=np.bool_),
    ],
)
def test_add_rejects_invalid_embedding_arrays(
    tmp_path: Path,
    embeddings: np.ndarray[Any, Any],
) -> None:
    # Arrange
    storage = ChromaStorage(_config(tmp_path / ".codescope"))

    # Act and Assert
    with pytest.raises(ValueError, match="Storage input is invalid"):
        storage.add_chunks([_chunk("a" * 64)], embeddings)


def test_add_safely_converts_numeric_embeddings_to_float32(tmp_path: Path) -> None:
    # Arrange
    storage = ChromaStorage(_config(tmp_path / ".codescope"))

    # Act
    storage.add_chunks([_chunk("a" * 64)], np.array([[1.0, 0.0]], dtype=np.float64))

    # Assert
    assert storage.count() == 1


def test_empty_add_is_an_explicit_collection_initialization(tmp_path: Path) -> None:
    # Arrange
    storage = ChromaStorage(_config(tmp_path / ".codescope"))

    # Act
    storage.add_chunks([], np.empty((0, 2), dtype=np.float32))

    # Assert
    assert storage.count() == 0


def test_add_rejects_duplicate_chunk_ids_before_writing(tmp_path: Path) -> None:
    # Arrange
    storage = ChromaStorage(_config(tmp_path / ".codescope"))
    duplicate = _chunk("a" * 64)

    # Act and Assert
    with pytest.raises(ValueError, match="Storage input is invalid"):
        storage.add_chunks(
            [duplicate, duplicate],
            np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
        )


@pytest.mark.parametrize(
    "query",
    [
        np.ones((2, 2), dtype=np.float32),
        np.ones((1, 1, 2), dtype=np.float32),
        np.array([np.nan, 0.0], dtype=np.float32),
        np.array([], dtype=np.float32),
    ],
)
def test_query_rejects_invalid_vector_shape_or_values(
    tmp_path: Path,
    query: np.ndarray[Any, Any],
) -> None:
    # Arrange
    storage = ChromaStorage(_config(tmp_path / ".codescope"))
    storage.initialize_collection()

    # Act and Assert
    with pytest.raises(ValueError, match="Storage input is invalid"):
        storage.query(query, limit=1)


@pytest.mark.parametrize("limit", [0, -1, True])
def test_query_rejects_invalid_limit(tmp_path: Path, limit: Any) -> None:
    # Arrange
    storage = ChromaStorage(_config(tmp_path / ".codescope"))

    # Act and Assert
    with pytest.raises(ValueError, match="Storage input is invalid"):
        storage.query(np.array([1.0, 0.0], dtype=np.float32), limit=limit)


def test_delete_by_file_removes_only_matching_chunks(tmp_path: Path) -> None:
    # Arrange
    storage = ChromaStorage(_config(tmp_path / ".codescope"))
    chunks = [_chunk("a" * 64), _chunk("b" * 64, file="src/other.py")]
    storage.add_chunks(chunks, np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32))

    # Act
    storage.delete_by_file("src/example.py")

    # Assert
    assert storage.count() == 1
    assert storage.query(np.array([0.0, 1.0], dtype=np.float32), limit=1)[0].file == "src/other.py"


def test_delete_by_file_rejects_unsafe_public_path(tmp_path: Path) -> None:
    # Arrange
    storage = ChromaStorage(_config(tmp_path / ".codescope"))

    # Act and Assert
    with pytest.raises(ValueError, match="Storage input is invalid"):
        storage.delete_by_file("../outside.py")


def test_missing_collection_read_fails_without_recreating_it(tmp_path: Path) -> None:
    # Arrange
    storage = ChromaStorage(_config(tmp_path / ".codescope"))

    # Act
    with pytest.raises(StorageFailedError) as error_info:
        storage.count()

    # Assert
    assert error_info.value.code is ErrorCode.STORAGE_FAILED
    assert str(error_info.value) == "The local CodeScope index is not initialized."
    assert storage._client.list_collections() == []


def test_chroma_failure_translation_does_not_leak_source_vector_or_runtime_path(
    tmp_path: Path,
) -> None:
    # Arrange
    source = "TOP_SECRET_SOURCE_BODY"
    vector_marker = "[0.123456789]"
    storage = ChromaStorage(_config(tmp_path / ".codescope"))

    class FailingClient:
        def get_collection(self, **_kwargs: object) -> object:
            raise OSError(f"{source} {vector_marker} {tmp_path}")

    storage._client = cast(Any, FailingClient())

    # Act
    with pytest.raises(StorageFailedError) as error_info:
        storage.count()

    # Assert
    message = str(error_info.value)
    assert message == "Local index storage could not complete the requested operation."
    assert source not in message
    assert vector_marker not in message
    assert str(tmp_path) not in message


def test_collection_reset_preserves_unrelated_runtime_files(tmp_path: Path) -> None:
    # Arrange
    runtime = tmp_path / ".codescope"
    storage = ChromaStorage(_config(runtime))
    storage.add_chunks([_chunk("a" * 64)], np.array([[1.0, 0.0]], dtype=np.float32))
    unrelated = runtime / "owner-notes.txt"
    unrelated.write_text("preserve", encoding="utf-8")

    # Act
    storage.reset_collection()

    # Assert
    assert storage.count() == 0
    assert unrelated.read_text(encoding="utf-8") == "preserve"
    assert runtime.is_dir()


def test_reset_of_missing_collection_initializes_empty_collection(tmp_path: Path) -> None:
    # Arrange
    storage = ChromaStorage(_config(tmp_path / ".codescope"))

    # Act
    storage.reset_collection()

    # Assert
    assert storage.count() == 0


def test_symbols_round_trip_as_validated_models(tmp_path: Path) -> None:
    # Arrange
    storage = ChromaStorage(_config(tmp_path / ".codescope"))
    symbols = [_symbol()]

    # Act
    storage.write_symbols(symbols)
    result = storage.read_symbols()

    # Assert
    assert result == symbols
    assert result[0] is not symbols[0]


def test_invalid_symbols_file_fails_safely_without_echoing_contents(tmp_path: Path) -> None:
    # Arrange
    secret = "DO_NOT_LEAK_JSON_CONTENT"
    runtime = tmp_path / ".codescope"
    storage = ChromaStorage(_config(runtime))
    (runtime / "symbols.json").write_text(f'{{"secret":"{secret}"}}', encoding="utf-8")

    # Act
    with pytest.raises(StorageFailedError) as error_info:
        storage.read_symbols()

    # Assert
    assert secret not in str(error_info.value)
    assert str(tmp_path) not in str(error_info.value)


def test_write_symbols_rejects_non_symbol_entries(tmp_path: Path) -> None:
    # Arrange
    storage = ChromaStorage(_config(tmp_path / ".codescope"))

    # Act and Assert
    with pytest.raises(ValueError, match="Storage input is invalid"):
        storage.write_symbols(["not-a-symbol"])  # type: ignore[list-item]


def test_index_metadata_round_trip_is_immutable_and_deterministic(tmp_path: Path) -> None:
    # Arrange
    runtime = tmp_path / ".codescope"
    storage = ChromaStorage(_config(runtime))
    metadata = _metadata()

    # Act
    storage.write_index_metadata(metadata)
    first_bytes = (runtime / "index_meta.json").read_bytes()
    storage.write_index_metadata(metadata)
    second_bytes = (runtime / "index_meta.json").read_bytes()
    result = storage.read_index_metadata()

    # Assert
    assert result == metadata
    assert first_bytes == second_bytes
    assert json.loads(first_bytes)["language_counts"] == {"python": 1}
    with pytest.raises(TypeError):
        result.language_counts["python"] = 2  # type: ignore[index]


def test_invalid_index_metadata_file_fails_safely(tmp_path: Path) -> None:
    # Arrange
    runtime = tmp_path / ".codescope"
    storage = ChromaStorage(_config(runtime))
    (runtime / "index_meta.json").write_text('{"schema_version":"wrong"}', encoding="utf-8")

    # Act and Assert
    with pytest.raises(StorageFailedError) as error_info:
        storage.read_index_metadata()
    assert str(tmp_path) not in str(error_info.value)


@pytest.mark.parametrize(
    "result",
    [
        {"ids": [], "documents": [], "metadatas": [], "distances": []},
        {
            "ids": [["a"]],
            "documents": [["text", "extra"]],
            "metadatas": [[{}]],
            "distances": [[0.1]],
        },
        {
            "ids": [["a"]],
            "documents": [["text"]],
            "metadatas": [["not-metadata"]],
            "distances": [[0.1]],
        },
    ],
)
def test_malformed_chroma_query_response_is_translated_safely(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    result: dict[str, object],
) -> None:
    # Arrange
    storage = ChromaStorage(_config(tmp_path / ".codescope"))

    class MalformedCollection:
        def query(self, **_kwargs: object) -> dict[str, object]:
            return result

    monkeypatch.setattr(storage, "_get_collection", lambda: MalformedCollection())

    # Act and Assert
    with pytest.raises(StorageFailedError) as error_info:
        storage.query(np.array([1.0, 0.0], dtype=np.float32), limit=1)
    assert (
        str(error_info.value) == "Local index storage could not complete the requested operation."
    )


def test_failed_serialization_preserves_previous_metadata_file(tmp_path: Path) -> None:
    # Arrange
    runtime = tmp_path / ".codescope"
    runtime.mkdir()
    destination = runtime / "symbols.json"
    destination.write_text("previous\n", encoding="utf-8")

    # Act
    with pytest.raises(TypeError):
        atomic_write_metadata_json(runtime, "symbols.json", object())

    # Assert
    assert destination.read_text(encoding="utf-8") == "previous\n"
    assert list(runtime.glob(".symbols.json.*.tmp")) == []


def test_failed_atomic_replace_preserves_previous_file_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    runtime = tmp_path / ".codescope"
    storage = ChromaStorage(_config(runtime))
    storage.write_symbols([_symbol()])
    previous = (runtime / "symbols.json").read_bytes()

    def fail_replace(_source: object, _destination: object) -> None:
        raise OSError("simulated safe write failure")

    monkeypatch.setattr("codescope.utils.json_io.os.replace", fail_replace)

    # Act
    with pytest.raises(StorageFailedError):
        storage.write_symbols([_symbol()])

    # Assert
    assert (runtime / "symbols.json").read_bytes() == previous
    assert list(runtime.glob(".symbols.json.*.tmp")) == []


@pytest.mark.parametrize("unsafe_name", ["../symbols.json", "nested/index_meta.json", "other.json"])
def test_atomic_writer_rejects_unknown_or_traversal_metadata_names(
    tmp_path: Path,
    unsafe_name: str,
) -> None:
    # Arrange
    runtime = tmp_path / ".codescope"
    runtime.mkdir()

    # Act and Assert
    with pytest.raises(ValueError, match="metadata path is unsafe"):
        atomic_write_metadata_json(runtime, unsafe_name, {})  # type: ignore[arg-type]
    assert list(tmp_path.rglob("*.json")) == []


def test_reset_can_remove_only_known_metadata_and_preserve_unrelated_file(tmp_path: Path) -> None:
    # Arrange
    runtime = tmp_path / ".codescope"
    storage = ChromaStorage(_config(runtime))
    storage.initialize_collection()
    storage.write_symbols([_symbol()])
    storage.write_index_metadata(_metadata())
    unrelated = runtime / "keep.txt"
    unrelated.write_text("keep", encoding="utf-8")

    # Act
    storage.reset_collection(remove_metadata=True)

    # Assert
    assert not (runtime / "symbols.json").exists()
    assert not (runtime / "index_meta.json").exists()
    assert unrelated.read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize(
    ("name", "maximum", "prefix", "expected"),
    [
        ("index_meta.json", INDEX_METADATA_MAX_BYTES, b"{}", {}),
        ("symbols.json", SYMBOLS_METADATA_MAX_BYTES, b"[]", []),
    ],
)
def test_metadata_reader_accepts_valid_json_one_byte_below_limit(
    tmp_path: Path,
    name: str,
    maximum: int,
    prefix: bytes,
    expected: object,
) -> None:
    # Arrange
    runtime = tmp_path / ".codescope"
    runtime.mkdir()
    (runtime / name).write_bytes(prefix + b" " * (maximum - 1 - len(prefix)))

    # Act
    result = read_metadata_json(runtime, name)  # type: ignore[arg-type]

    # Assert
    assert result == expected


@pytest.mark.parametrize(
    ("name", "maximum"),
    [
        ("index_meta.json", INDEX_METADATA_MAX_BYTES),
        ("symbols.json", SYMBOLS_METADATA_MAX_BYTES),
    ],
)
def test_metadata_reader_rejects_file_one_byte_above_limit(
    tmp_path: Path,
    name: str,
    maximum: int,
) -> None:
    # Arrange
    runtime = tmp_path / ".codescope"
    runtime.mkdir()
    (runtime / name).write_bytes(b"[]" + b" " * (maximum - 1))

    # Act and Assert
    with pytest.raises(InvalidPathError, match="safe size limit"):
        read_metadata_json(runtime, name)  # type: ignore[arg-type]
