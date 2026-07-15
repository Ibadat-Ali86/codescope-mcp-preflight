"""Security regression tests for Phase 4 model and storage boundaries."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from codescope.config import EmbeddingsConfig, StorageConfig
from codescope.embedder import LocalEmbedder
from codescope.exceptions import StorageFailedError
from codescope.models import CodeChunk
from codescope.storage import ChromaStorage
from codescope.utils.json_io import atomic_write_metadata_json


def _storage(path: Path) -> ChromaStorage:
    return ChromaStorage(StorageConfig(path=path, collection="codescope_chunks"))


def _chunk(text: str = "SECRET_VALUE = 1\n") -> CodeChunk:
    return CodeChunk(
        id="a" * 64,
        text=text,
        file="src/private.py",
        start_line=1,
        end_line=1,
        language="python",
        symbol_name=None,
        qualified_name=None,
        chunk_index=0,
        content_hash="b" * 64,
    )


def test_runtime_symlink_escape_is_rejected_without_path_leak(tmp_path: Path) -> None:
    # Arrange
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "runtime"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlink creation unavailable on this operating system: {error}")
    unsafe = StorageConfig.model_construct(path=link, collection="codescope_chunks")

    # Act
    with pytest.raises(StorageFailedError) as error_info:
        ChromaStorage(unsafe)

    # Assert
    assert str(tmp_path) not in str(error_info.value)
    assert "runtime" not in str(error_info.value)


def test_metadata_symlink_cannot_read_or_replace_external_content(tmp_path: Path) -> None:
    # Arrange
    runtime = tmp_path / ".codescope"
    storage = _storage(runtime)
    external = tmp_path / "external.json"
    external.write_text('"TOP_SECRET_EXTERNAL"', encoding="utf-8")
    link = runtime / "symbols.json"
    try:
        link.symlink_to(external)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlink creation unavailable on this operating system: {error}")

    # Act and Assert
    with pytest.raises(StorageFailedError):
        storage.read_symbols()
    with pytest.raises(StorageFailedError):
        storage.write_symbols([])
    assert external.read_text(encoding="utf-8") == '"TOP_SECRET_EXTERNAL"'


@pytest.mark.parametrize("name", ["../symbols.json", "/tmp/index_meta.json", "x/y.json"])
def test_metadata_writer_has_no_arbitrary_path_or_traversal_escape(
    tmp_path: Path,
    name: str,
) -> None:
    # Arrange
    runtime = tmp_path / ".codescope"
    runtime.mkdir()

    # Act and Assert
    with pytest.raises(ValueError):
        atomic_write_metadata_json(runtime, name, {})  # type: ignore[arg-type]
    assert list(tmp_path.rglob("*.json")) == []


def test_collection_reset_never_recursively_deletes_runtime_or_repository_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    storage = _storage(tmp_path)
    storage.initialize_collection()
    protected = tmp_path / "repository-content.py"
    protected.write_text("VALUE = 1\n", encoding="utf-8")

    def reject_recursive_delete(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("recursive deletion attempted")

    monkeypatch.setattr(shutil, "rmtree", reject_recursive_delete)

    # Act
    storage.reset_collection(remove_metadata=True)

    # Assert
    assert tmp_path.is_dir()
    assert protected.read_text(encoding="utf-8") == "VALUE = 1\n"


def test_normal_query_requests_no_embeddings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    storage = _storage(tmp_path / ".codescope")
    storage.add_chunks([_chunk()], np.array([[1.0, 0.0]], dtype=np.float32))
    collection = storage._get_collection()
    observed_include: list[str] = []
    original_query = collection.query

    def spy_query(**kwargs: Any) -> object:
        observed_include.extend(kwargs["include"])
        return original_query(**kwargs)

    monkeypatch.setattr(collection, "query", spy_query)
    monkeypatch.setattr(storage, "_get_collection", lambda: collection)

    # Act
    matches = storage.query(np.array([1.0, 0.0], dtype=np.float32), limit=1)

    # Assert
    assert observed_include == ["documents", "metadatas", "distances"]
    assert "embeddings" not in observed_include
    assert not hasattr(matches[0], "embeddings")


def test_storage_errors_and_logs_exclude_source_vector_and_absolute_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Arrange
    source = "TOP_SECRET_FUNCTION_BODY"
    vector = np.array([[np.nan, 0.123456789]], dtype=np.float32)
    storage = _storage(tmp_path / ".codescope")

    # Act
    with pytest.raises(ValueError) as error_info:
        storage.add_chunks([_chunk(source)], vector)

    # Assert
    message = str(error_info.value)
    captured = capsys.readouterr()
    combined = message + captured.out + captured.err
    assert source not in combined
    assert "0.123456789" not in combined
    assert str(tmp_path) not in combined


def test_download_disabled_model_path_forwards_cache_only_without_network_side_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)
    before = set(tmp_path.rglob("*"))
    observed: dict[str, object] = {}

    class CacheMissFactory:
        def __call__(
            self,
            model_name: str,
            *,
            device: str,
            local_files_only: bool,
        ) -> object:
            observed.update(
                model_name=model_name,
                device=device,
                local_files_only=local_files_only,
            )
            raise OSError("offline cache miss")

    config = EmbeddingsConfig(
        model="uncached/test-model",
        batch_size=2,
        device="cpu",
        normalize=True,
    )
    embedder = LocalEmbedder(config, allow_download=False, model_factory=CacheMissFactory())

    # Act
    with pytest.raises(RuntimeError, match="unavailable locally"):
        embedder.encode(["safe input"])

    # Assert
    assert observed["local_files_only"] is True
    assert set(tmp_path.rglob("*")) == before


def test_chroma_telemetry_is_disabled_for_local_persistent_client(tmp_path: Path) -> None:
    # Arrange and Act
    storage = _storage(tmp_path / ".codescope")

    # Assert
    assert storage._settings.anonymized_telemetry is False
