"""Security and rollback tests for Phase 5 repository indexing."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import codescope.indexer as indexer_module
import codescope.utils.json_io as json_io_module
from codescope.chunker import TokenOffset
from codescope.config import (
    AppConfig,
    EmbeddingsConfig,
    IndexConfig,
    SearchConfig,
    ServerConfig,
    StorageConfig,
)
from codescope.exceptions import InvalidPathError, StorageFailedError
from codescope.indexer import (
    RepositoryIndexer,
    RepositoryScanner,
    SkippedFile,
    SkipReason,
    _cleanup_generated_directory,
)
from codescope.models import CodeChunk
from codescope.storage import ChromaStorage
from codescope.utils.json_io import read_metadata_json

TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


class SafeTokenizer:
    def count_wordpieces(self, text: str) -> int:
        return len(TOKEN_PATTERN.findall(text))

    def wordpiece_offsets(self, text: str) -> Sequence[TokenOffset]:
        return tuple(match.span() for match in TOKEN_PATTERN.finditer(text))


class SafeEmbedder:
    tokenizer = SafeTokenizer()

    def encode(self, texts: Sequence[str]) -> np.ndarray[Any, Any]:
        vectors = np.zeros((len(texts), 2), dtype=np.float32)
        if len(texts):
            vectors[:, 0] = 1.0
        return vectors


class _FakeDirectoryEntry:
    def __init__(self, name: str) -> None:
        self.name = name


class _CountingScandir:
    def __init__(self) -> None:
        self.consumed = 0

    def __enter__(self) -> _CountingScandir:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def __iter__(self) -> _CountingScandir:
        return self

    def __next__(self) -> _FakeDirectoryEntry:
        self.consumed += 1
        return _FakeDirectoryEntry(f"entry-{self.consumed:04d}")


def _config(root: Path, runtime: Path, *, follow: bool = False) -> AppConfig:
    return AppConfig(
        server=ServerConfig(name="codescope", transport="stdio"),
        index=IndexConfig(
            root=root,
            languages=("python",),
            include_extensions=(".py", ".pyi"),
            exclude=(".git", ".codescope", ".venv", "__pycache__"),
            max_file_size_kb=1,
            max_chunk_wordpieces=80,
            chunk_overlap_wordpieces=5,
            follow_symlinks=follow,
        ),
        embeddings=EmbeddingsConfig(
            model="sentence-transformers/all-MiniLM-L6-v2",
            batch_size=2,
            device="cpu",
            normalize=True,
        ),
        storage=StorageConfig(path=runtime, collection="codescope_chunks"),
        search=SearchConfig(default_limit=5, maximum_limit=20, minimum_query_characters=2),
    )


def _write(path: Path, text: str = "VALUE = 1\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build_healthy(config: AppConfig) -> int:
    return RepositoryIndexer(config, embedder=SafeEmbedder()).rebuild().total_chunks


def _assert_old_index(config: AppConfig, expected_chunks: int) -> None:
    assert RepositoryIndexer(config).status().total_chunks == expected_chunks
    assert list(config.storage.path.parent.glob(f"{config.storage.path.name}.build-*")) == []
    assert list(config.storage.path.parent.glob(f"{config.storage.path.name}.backup-*")) == []


def test_directory_entry_bound_precedes_full_iterator_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    iterator = _CountingScandir()
    monkeypatch.setattr(indexer_module.os, "scandir", lambda _path: iterator)

    # Act and Assert
    with pytest.raises(indexer_module._DirectoryEntryLimitExceeded):
        indexer_module._bounded_sorted_entries(tmp_path, remaining=2)
    assert iterator.consumed == 3


def test_read_race_is_bounded_to_maximum_plus_detection_byte(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    path = tmp_path / "race.py"
    path.write_bytes(b"VALUE = 1\n")
    config = _config(tmp_path, tmp_path / ".codescope")
    scanner = RepositoryScanner(config.index, runtime_path=config.storage.path)
    source_file = scanner.discover(tmp_path).files[0]
    original_read = indexer_module.os.read
    requests: list[int] = []
    raced = False

    def racing_read(descriptor: int, amount: int) -> bytes:
        nonlocal raced
        requests.append(amount)
        if not raced:
            raced = True
            with path.open("ab") as output:
                output.write(b"x" * 2048)
        return original_read(descriptor, amount)

    monkeypatch.setattr(indexer_module.os, "read", racing_read)

    # Act
    result = scanner.read(source_file, tmp_path)

    # Assert
    assert result == SkippedFile("race.py", SkipReason.OVERSIZED)
    assert sum(requests) <= 1025


def test_scanner_errors_and_progress_never_expose_source_or_absolute_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Arrange
    secret = "TOP_SECRET_PHASE5_SOURCE"
    _write(tmp_path / "secret.py", f"{secret} = 1\n")
    config = _config(tmp_path, tmp_path / ".codescope")

    class FailingEmbedder(SafeEmbedder):
        def encode(self, texts: Sequence[str]) -> np.ndarray[Any, Any]:
            raise RuntimeError(texts[0])

    # Act
    with pytest.raises(StorageFailedError) as error_info:
        RepositoryIndexer(config, embedder=FailingEmbedder()).rebuild()

    # Assert
    captured = capsys.readouterr()
    combined = str(error_info.value) + captured.out + captured.err
    assert secret not in combined
    assert str(tmp_path) not in combined


def test_generated_cleanup_accepts_only_exact_build_and_backup_siblings(tmp_path: Path) -> None:
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    parent = root
    valid_build = parent / ".codescope.build-abcdef"
    valid_backup = parent / ".codescope.backup-abcdef"
    valid_build.mkdir()
    valid_backup.mkdir()
    _write(valid_build / "nested/value.txt", "safe\n")

    # Act
    _cleanup_generated_directory(
        valid_build,
        runtime_parent=parent,
        repository_root=root,
        live_name=".codescope",
    )
    _cleanup_generated_directory(
        valid_backup,
        runtime_parent=parent,
        repository_root=root,
        live_name=".codescope",
    )

    # Assert
    assert not valid_build.exists()
    assert not valid_backup.exists()


@pytest.mark.parametrize(
    "candidate_name",
    [".codescope", ".codescope.build", ".codescope.build-confusion.txt", "other.build-abcdef"],
)
def test_generated_cleanup_rejects_name_prefix_confusion(
    tmp_path: Path,
    candidate_name: str,
) -> None:
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    candidate = root / candidate_name
    candidate.mkdir()

    # Act and Assert
    with pytest.raises(InvalidPathError):
        _cleanup_generated_directory(
            candidate,
            runtime_parent=root,
            repository_root=root,
            live_name=".codescope",
        )
    assert candidate.exists()


def test_generated_cleanup_rejects_repository_root_and_parent(tmp_path: Path) -> None:
    # Arrange
    root = tmp_path / ".codescope.build-abcdef"
    root.mkdir()

    # Act and Assert
    with pytest.raises(InvalidPathError):
        _cleanup_generated_directory(
            root,
            runtime_parent=root,
            repository_root=root,
            live_name=".codescope",
        )
    assert root.exists()


def test_generated_cleanup_rejects_external_symlink_and_preserves_target(tmp_path: Path) -> None:
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    marker = external / "marker.txt"
    marker.write_text("preserve", encoding="utf-8")
    candidate = root / ".codescope.build-abcdef"
    try:
        candidate.symlink_to(external, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlink creation unavailable on this operating system: {error}")

    # Act and Assert
    with pytest.raises(InvalidPathError):
        _cleanup_generated_directory(
            candidate,
            runtime_parent=root,
            repository_root=root,
            live_name=".codescope",
        )
    assert marker.read_text(encoding="utf-8") == "preserve"


def test_generated_cleanup_unlinks_nested_symlink_without_following_it(tmp_path: Path) -> None:
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    marker = external / "marker.txt"
    marker.write_text("preserve", encoding="utf-8")
    candidate = root / ".codescope.build-abcdef"
    candidate.mkdir()
    try:
        (candidate / "nested-link").symlink_to(external, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlink creation unavailable on this operating system: {error}")

    # Act
    _cleanup_generated_directory(
        candidate,
        runtime_parent=root,
        repository_root=root,
        live_name=".codescope",
    )

    # Assert
    assert not candidate.exists()
    assert marker.read_text(encoding="utf-8") == "preserve"


def test_temporary_verification_failure_preserves_previous_live_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    _write(tmp_path / "value.py")
    config = _config(tmp_path, tmp_path / ".codescope")
    expected = _build_healthy(config)
    indexer = RepositoryIndexer(config, embedder=SafeEmbedder())
    monkeypatch.setattr(indexer, "_verify", lambda *_args: (_ for _ in ()).throw(ValueError()))

    # Act and Assert
    with pytest.raises(StorageFailedError):
        indexer.rebuild()
    _assert_old_index(config, expected)


def test_scanner_failure_cleans_temporary_build_and_preserves_live_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    _write(tmp_path / "value.py")
    config = _config(tmp_path, tmp_path / ".codescope")
    expected = _build_healthy(config)

    def fail_scan(*_args: object, **_kwargs: object) -> None:
        raise OSError("private scanner detail")

    monkeypatch.setattr(indexer_module.RepositoryScanner, "discover", fail_scan)

    # Act and Assert
    with pytest.raises(StorageFailedError) as error_info:
        RepositoryIndexer(config, embedder=SafeEmbedder()).rebuild()
    assert str(tmp_path) not in str(error_info.value)
    _assert_old_index(config, expected)


def test_chunker_programming_failure_aborts_without_replacing_live_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    _write(tmp_path / "value.py")
    config = _config(tmp_path, tmp_path / ".codescope")
    expected = _build_healthy(config)

    def fail_chunk(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("chunker programming defect")

    monkeypatch.setattr(indexer_module.CodeChunker, "chunk", fail_chunk)

    # Act and Assert
    with pytest.raises(AssertionError, match="programming defect"):
        RepositoryIndexer(config, embedder=SafeEmbedder()).rebuild()
    _assert_old_index(config, expected)


@pytest.mark.parametrize("method_name", ["add_chunks", "write_symbols", "write_index_metadata"])
def test_storage_stage_failure_aborts_and_preserves_live_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
) -> None:
    # Arrange
    _write(tmp_path / "value.py")
    config = _config(tmp_path, tmp_path / ".codescope")
    expected = _build_healthy(config)

    def fail_storage(*_args: object, **_kwargs: object) -> None:
        raise StorageFailedError("safe simulated storage failure")

    monkeypatch.setattr(ChromaStorage, method_name, fail_storage)

    # Act and Assert
    with pytest.raises(StorageFailedError):
        RepositoryIndexer(config, embedder=SafeEmbedder()).rebuild()
    _assert_old_index(config, expected)


def test_duplicate_chunk_identifier_aborts_before_storage_corruption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    _write(tmp_path / "one.py")
    _write(tmp_path / "two.py")
    config = _config(tmp_path, tmp_path / ".codescope")
    expected = _build_healthy(config)
    duplicate = CodeChunk(
        id="a" * 64,
        text="VALUE = 1\n",
        file="one.py",
        start_line=1,
        end_line=1,
        language="python",
        symbol_name=None,
        qualified_name=None,
        chunk_index=0,
        content_hash="b" * 64,
    )
    monkeypatch.setattr(
        indexer_module.CodeChunker,
        "chunk",
        lambda *_args, **_kwargs: [duplicate],
    )

    # Act and Assert
    with pytest.raises(StorageFailedError):
        RepositoryIndexer(config, embedder=SafeEmbedder()).rebuild()
    _assert_old_index(config, expected)


def test_live_to_backup_failure_preserves_previous_live_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    _write(tmp_path / "value.py")
    runtime = tmp_path / ".codescope"
    config = _config(tmp_path, runtime)
    expected = _build_healthy(config)
    original_replace = indexer_module.os.replace

    def fail_live(source: Path, destination: Path) -> None:
        if Path(source) == runtime:
            raise OSError("simulated rename failure")
        original_replace(source, destination)

    monkeypatch.setattr(indexer_module.os, "replace", fail_live)

    # Act and Assert
    with pytest.raises(StorageFailedError):
        RepositoryIndexer(config, embedder=SafeEmbedder()).rebuild()
    _assert_old_index(config, expected)


def test_temporary_to_live_failure_restores_previous_live_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    _write(tmp_path / "value.py")
    runtime = tmp_path / ".codescope"
    config = _config(tmp_path, runtime)
    expected = _build_healthy(config)
    original_replace = indexer_module.os.replace

    def fail_promotion(source: Path, destination: Path) -> None:
        if ".build-" in Path(source).name and Path(destination) == runtime:
            raise OSError("simulated promotion failure")
        original_replace(source, destination)

    monkeypatch.setattr(indexer_module.os, "replace", fail_promotion)

    # Act and Assert
    with pytest.raises(StorageFailedError):
        RepositoryIndexer(config, embedder=SafeEmbedder()).rebuild()
    _assert_old_index(config, expected)


def test_promoted_verification_failure_rolls_back_previous_live_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    _write(tmp_path / "value.py")
    config = _config(tmp_path, tmp_path / ".codescope")
    expected = _build_healthy(config)
    indexer = RepositoryIndexer(config, embedder=SafeEmbedder())
    original_verify = indexer._verify
    calls = 0

    def fail_second(*args: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise StorageFailedError("safe verification failure")
        original_verify(*args)  # type: ignore[arg-type]

    monkeypatch.setattr(indexer, "_verify", fail_second)

    # Act and Assert
    with pytest.raises(StorageFailedError):
        indexer.rebuild()
    _assert_old_index(config, expected)


def test_backup_cleanup_failure_rolls_back_previous_live_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    _write(tmp_path / "value.py")
    config = _config(tmp_path, tmp_path / ".codescope")
    expected = _build_healthy(config)
    original_cleanup = indexer_module._cleanup_generated_directory
    failed = False

    def fail_backup(candidate: Path, **kwargs: object) -> None:
        nonlocal failed
        if ".backup-" in candidate.name and not failed:
            failed = True
            raise InvalidPathError("safe cleanup failure")
        original_cleanup(candidate, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(indexer_module, "_cleanup_generated_directory", fail_backup)

    # Act and Assert
    with pytest.raises(StorageFailedError):
        RepositoryIndexer(config, embedder=SafeEmbedder()).rebuild()
    _assert_old_index(config, expected)


def test_oversized_metadata_and_metadata_read_race_are_rejected_safely(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange: one fixed metadata path with a size-change race
    runtime = tmp_path / ".codescope"
    runtime.mkdir()
    metadata = runtime / "index_meta.json"
    metadata.write_bytes(b"{}")
    original_read = json_io_module.os.read
    raced = False

    def racing_read(descriptor: int, amount: int) -> bytes:
        nonlocal raced
        block = original_read(descriptor, amount)
        if not raced:
            raced = True
            with metadata.open("ab") as output:
                output.write(b" ")
        return block

    monkeypatch.setattr(json_io_module.os, "read", racing_read)

    # Act and Assert
    with pytest.raises(InvalidPathError) as error_info:
        read_metadata_json(runtime, "index_meta.json")
    assert str(tmp_path) not in str(error_info.value)


@pytest.mark.parametrize("allow_download", [False, True])
def test_indexing_forwards_only_explicit_model_download_permission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    allow_download: bool,
) -> None:
    # Arrange
    _write(tmp_path / "value.py")
    config = _config(tmp_path, tmp_path / ".codescope")
    observed: list[bool] = []

    class CacheOnlyEmbedder(SafeEmbedder):
        def __init__(self, _config: object, *, allow_download: bool) -> None:
            observed.append(allow_download)

    monkeypatch.setattr(indexer_module, "LocalEmbedder", CacheOnlyEmbedder)

    # Act
    RepositoryIndexer(config).rebuild(allow_model_download=allow_download)

    # Assert
    assert observed == [allow_download]


def test_cache_miss_has_fixed_actionable_message_without_backend_detail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    _write(tmp_path / "value.py")
    config = _config(tmp_path, tmp_path / ".codescope")
    backend_secret = "PRIVATE_CACHE_LOCATION"

    class MissingModel:
        def __init__(self, _config: object, *, allow_download: bool) -> None:
            assert allow_download is False

        @property
        def tokenizer(self) -> SafeTokenizer:
            raise RuntimeError("The embedding model is unavailable locally. " + backend_secret)

    monkeypatch.setattr(indexer_module, "LocalEmbedder", MissingModel)

    # Act
    with pytest.raises(StorageFailedError) as error_info:
        RepositoryIndexer(config).rebuild()

    # Assert
    assert str(error_info.value) == "The embedding model is unavailable locally."
    assert "--allow-model-download" in error_info.value.suggestion
    assert backend_secret not in str(error_info.value)


def test_no_graphify_path_is_created_by_indexing(tmp_path: Path) -> None:
    # Arrange
    _write(tmp_path / "value.py")
    config = _config(tmp_path, tmp_path / ".codescope")

    # Act
    RepositoryIndexer(config, embedder=SafeEmbedder()).rebuild()

    # Assert
    assert not (tmp_path / "graphify-out").exists()
