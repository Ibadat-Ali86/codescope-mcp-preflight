"""Tests for deterministic scanning and transactional repository indexing."""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any, NoReturn

import numpy as np
import pytest

import codescope.indexer as indexer_module
from codescope.chunker import TokenOffset
from codescope.config import (
    AppConfig,
    EmbeddingsConfig,
    IndexConfig,
    SearchConfig,
    ServerConfig,
    StorageConfig,
)
from codescope.exceptions import (
    IndexNotFoundError,
    InvalidPathError,
    ParseFailedError,
    StorageFailedError,
)
from codescope.indexer import (
    ProgressEvent,
    RepositoryIndexer,
    RepositoryScanner,
    SkippedFile,
    SkipReason,
    _configuration_fingerprint,
)
from codescope.models import Symbol
from codescope.parser import CodeParser
from codescope.storage import ChromaStorage, IndexMetadata

TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


class FakeTokenizer:
    def count_wordpieces(self, text: str) -> int:
        return len(TOKEN_PATTERN.findall(text))

    def wordpiece_offsets(self, text: str) -> Sequence[TokenOffset]:
        return tuple(match.span() for match in TOKEN_PATTERN.finditer(text))


class FakeEmbedder:
    tokenizer = FakeTokenizer()

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, ...]] = []

    def encode(self, texts: Sequence[str]) -> np.ndarray[Any, Any]:
        self.calls.append(tuple(texts))
        if self.fail:
            raise RuntimeError("private model detail")
        vectors = np.zeros((len(texts), 3), dtype=np.float32)
        if len(texts):
            vectors[:, 0] = 1.0
        return vectors


def _config(
    root: Path,
    runtime: Path,
    *,
    maximum_kb: int = 1,
    batch_size: int = 2,
    follow_symlinks: bool = False,
    exclude: tuple[str, ...] = (".git", ".codescope", ".venv", "__pycache__"),
) -> AppConfig:
    return AppConfig(
        server=ServerConfig(name="codescope", transport="stdio"),
        index=IndexConfig(
            root=root,
            languages=("python",),
            include_extensions=(".py", ".pyi"),
            exclude=exclude,
            max_file_size_kb=maximum_kb,
            max_chunk_wordpieces=80,
            chunk_overlap_wordpieces=5,
            follow_symlinks=follow_symlinks,
        ),
        embeddings=EmbeddingsConfig(
            model="sentence-transformers/all-MiniLM-L6-v2",
            batch_size=batch_size,
            device="cpu",
            normalize=True,
        ),
        storage=StorageConfig(path=runtime, collection="codescope_chunks"),
        search=SearchConfig(default_limit=5, maximum_limit=20, minimum_query_characters=2),
    )


def _scanner(config: AppConfig) -> RepositoryScanner:
    return RepositoryScanner(config.index, runtime_path=config.storage.path)


def _write(path: Path, text: str = "VALUE = 1\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _symlink(link: Path, target: Path, *, directory: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlink creation unavailable on this operating system: {error}")


def test_scanner_empty_repository_is_deterministic(tmp_path: Path) -> None:
    # Arrange
    config = _config(tmp_path, tmp_path / ".codescope")

    # Act
    first = _scanner(config).discover(tmp_path)
    second = _scanner(config).discover(tmp_path)

    # Assert
    assert first == second
    assert first.files == ()


def test_scanner_directory_and_entry_tracking_are_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    (tmp_path / "directory").mkdir()
    config = _config(tmp_path, tmp_path / ".codescope")
    monkeypatch.setattr(indexer_module, "_MAX_SCAN_DIRECTORIES", 1)

    # Act and Assert
    with pytest.raises(InvalidPathError, match="scanned safely"):
        _scanner(config).discover(tmp_path)

    # Arrange: bound total entries independently
    monkeypatch.setattr(indexer_module, "_MAX_SCAN_DIRECTORIES", 100)
    monkeypatch.setattr(indexer_module, "_MAX_SCAN_ENTRIES", 0)

    # Act and Assert
    with pytest.raises(InvalidPathError, match="scanned safely"):
        _scanner(config).discover(tmp_path)


def test_scanner_accepts_python_and_stub_files_in_sorted_posix_order(tmp_path: Path) -> None:
    # Arrange
    _write(tmp_path / "z.py")
    _write(tmp_path / "nested/a.pyi", "VALUE: int\n")
    config = _config(tmp_path, tmp_path / ".codescope")

    # Act
    result = _scanner(config).discover(tmp_path)

    # Assert
    assert [item.relative_path for item in result.files] == ["nested/a.pyi", "z.py"]
    assert all("\\" not in item.relative_path for item in result.files)


def test_scanner_records_unsupported_extension_and_directory_masquerade(tmp_path: Path) -> None:
    # Arrange
    _write(tmp_path / "notes.txt")
    (tmp_path / "fake.py").mkdir()
    config = _config(tmp_path, tmp_path / ".codescope")

    # Act
    result = _scanner(config).discover(tmp_path)

    # Assert
    reasons = {item.relative_path: item.reason for item in result.skipped}
    assert reasons["notes.txt"] is SkipReason.UNSUPPORTED_EXTENSION
    assert reasons["fake.py"] is SkipReason.NOT_REGULAR


def test_configured_and_root_gitignore_exclusions_are_applied(tmp_path: Path) -> None:
    # Arrange
    _write(tmp_path / "configured/drop.py")
    _write(tmp_path / "ignored.py")
    _write(tmp_path / "keep.py")
    (tmp_path / ".gitignore").write_text("*.py\n!keep.py\n", encoding="utf-8")
    config = _config(
        tmp_path,
        tmp_path / ".codescope",
        exclude=("configured/",),
    )

    # Act
    result = _scanner(config).discover(tmp_path)

    # Assert
    assert [item.relative_path for item in result.files] == ["keep.py"]
    reasons = {item.relative_path: item.reason for item in result.skipped}
    assert reasons["configured"] is SkipReason.EXCLUDED
    assert reasons["ignored.py"] is SkipReason.GITIGNORED


@pytest.mark.parametrize(
    "relative",
    [
        ".env",
        ".env.production",
        "id_rsa",
        "private_key.py",
        "certificate.pem",
        "archive.zip",
        "image.png",
        "generated.sqlite3",
        ".codescope/index.py",
        ".cache/huggingface/model.py",
        "node_modules/package.py",
        "dist/output.py",
    ],
)
def test_scanner_hard_exclusions_cannot_be_reenabled(tmp_path: Path, relative: str) -> None:
    # Arrange
    _write(tmp_path / relative)
    (tmp_path / ".gitignore").write_text(f"!{relative}\n", encoding="utf-8")
    config = _config(tmp_path, tmp_path / "runtime")

    # Act
    result = _scanner(config).discover(tmp_path)

    # Assert
    assert all(item.relative_path != relative for item in result.files)
    assert any(item.reason is SkipReason.EXCLUDED for item in result.skipped)


def test_scanner_enforces_exact_size_boundary(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "exact.py").write_bytes(b"x" * 1024)
    (tmp_path / "large.py").write_bytes(b"x" * 1025)
    config = _config(tmp_path, tmp_path / ".codescope", maximum_kb=1)

    # Act
    result = _scanner(config).discover(tmp_path)

    # Assert
    assert [item.relative_path for item in result.files] == ["exact.py"]
    assert SkippedFile("large.py", SkipReason.OVERSIZED) in result.skipped


@pytest.mark.parametrize(
    ("payload", "reason"),
    [(b"VALUE = b'\x00'\n\x00", SkipReason.BINARY), (b"\xff\xfe", SkipReason.UNDECODABLE)],
)
def test_scanner_descriptor_read_rejects_binary_and_invalid_utf8(
    tmp_path: Path,
    payload: bytes,
    reason: SkipReason,
) -> None:
    # Arrange
    path = tmp_path / "unsafe.py"
    path.write_bytes(payload)
    config = _config(tmp_path, tmp_path / ".codescope")
    scanner = _scanner(config)
    source_file = scanner.discover(tmp_path).files[0]

    # Act
    result = scanner.read(source_file, tmp_path)

    # Assert
    assert result == SkippedFile("unsafe.py", reason)


def test_scanner_detects_file_change_between_discovery_and_read(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "changed.py"
    _write(path)
    config = _config(tmp_path, tmp_path / ".codescope")
    scanner = _scanner(config)
    source_file = scanner.discover(tmp_path).files[0]
    path.write_text("CHANGED = 2\n", encoding="utf-8")

    # Act
    result = scanner.read(source_file, tmp_path)

    # Assert
    assert result == SkippedFile("changed.py", SkipReason.UNREADABLE)


def test_scanner_rejects_symlink_by_default_and_external_when_following(tmp_path: Path) -> None:
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    external = tmp_path / "external.py"
    _write(external)
    link = root / "linked.py"
    _symlink(link, external)

    # Act
    disabled = _scanner(_config(root, root / ".codescope")).discover(root)
    enabled = _scanner(_config(root, root / ".codescope", follow_symlinks=True)).discover(root)

    # Assert
    assert SkippedFile("linked.py", SkipReason.SYMLINK_DISABLED) in disabled.skipped
    assert SkippedFile("linked.py", SkipReason.OUTSIDE_ROOT) in enabled.skipped


def test_scanner_follows_one_contained_symlink_without_duplicate_target(tmp_path: Path) -> None:
    # Arrange
    target = tmp_path / "target.py"
    _write(target)
    alias = tmp_path / "alias.py"
    _symlink(alias, target)
    config = _config(tmp_path, tmp_path / ".codescope", follow_symlinks=True)

    # Act
    result = _scanner(config).discover(tmp_path)

    # Assert
    assert len(result.files) == 1
    assert result.files[0].relative_path == "alias.py"
    assert SkippedFile("target.py", SkipReason.DUPLICATE) in result.skipped


def test_scanner_symlink_directory_cycle_terminates(tmp_path: Path) -> None:
    # Arrange
    directory = tmp_path / "source"
    directory.mkdir()
    _write(directory / "value.py")
    _symlink(directory / "cycle", directory, directory=True)
    config = _config(tmp_path, tmp_path / ".codescope", follow_symlinks=True)

    # Act
    result = _scanner(config).discover(tmp_path)

    # Assert
    assert [item.relative_path for item in result.files] == ["source/value.py"]
    assert any(item.reason is SkipReason.DUPLICATE for item in result.skipped)


def test_scanner_follows_contained_directory_link_and_rejects_external_directory_link(
    tmp_path: Path,
) -> None:
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    internal = root / "target"
    internal.mkdir()
    _write(internal / "value.py")
    external = tmp_path / "external"
    external.mkdir()
    _write(external / "outside.py")
    _symlink(root / "a-internal", internal, directory=True)
    _symlink(root / "z-external", external, directory=True)
    config = _config(root, root / ".codescope", follow_symlinks=True)

    # Act
    result = _scanner(config).discover(root)

    # Assert
    assert [item.relative_path for item in result.files] == ["a-internal/value.py"]
    assert SkippedFile("target", SkipReason.DUPLICATE) in result.skipped
    assert SkippedFile("z-external", SkipReason.OUTSIDE_ROOT) in result.skipped


def test_scanner_never_indexes_configured_runtime_directory(tmp_path: Path) -> None:
    # Arrange
    runtime = tmp_path / "runtime-data"
    _write(runtime / "should_not_index.py")
    _write(tmp_path / "keep.py")
    config = _config(tmp_path, runtime)

    # Act
    result = _scanner(config).discover(tmp_path)

    # Assert
    assert [item.relative_path for item in result.files] == ["keep.py"]


def test_indexer_constructor_performs_no_parser_model_or_storage_work(tmp_path: Path) -> None:
    # Arrange
    config = _config(tmp_path, tmp_path / ".codescope")

    def unexpected_storage(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("storage opened")

    # Act
    indexer = RepositoryIndexer(config, storage_factory=unexpected_storage)  # type: ignore[arg-type]

    # Assert
    assert isinstance(indexer, RepositoryIndexer)


def test_empty_repository_builds_consistent_empty_index(tmp_path: Path) -> None:
    # Arrange
    config = _config(tmp_path, tmp_path / ".codescope")
    indexer = RepositoryIndexer(config, embedder=FakeEmbedder())

    # Act
    summary = indexer.rebuild()
    status = indexer.status()

    # Assert
    assert (summary.total_files, summary.total_symbols, summary.total_chunks) == (0, 0, 0)
    assert status.index_exists is True
    assert status.index_root == "."


def test_single_file_pipeline_persists_symbols_chunks_and_formatted_inputs(
    tmp_path: Path,
) -> None:
    # Arrange
    _write(tmp_path / "value.py", "def value() -> int:\n    return 1\n")
    config = _config(tmp_path, tmp_path / ".codescope")
    embedder = FakeEmbedder()
    indexer = RepositoryIndexer(config, embedder=embedder)

    # Act
    summary = indexer.rebuild()
    storage = ChromaStorage(config.storage, create=False)
    try:
        symbols = storage.read_symbols()
        metadata = storage.read_index_metadata()
        count = storage.count()
    finally:
        storage.close()

    # Assert
    assert summary.total_files == 1
    assert [symbol.qualified_name for symbol in symbols] == ["value"]
    assert metadata.chunk_count == count == summary.total_chunks
    assert any("symbol: value" in text for batch in embedder.calls for text in batch)


def test_embedding_batches_preserve_configured_bound_and_global_count(tmp_path: Path) -> None:
    # Arrange
    for index in range(5):
        _write(tmp_path / f"value_{index}.py", f"VALUE_{index} = {index}\n")
    config = _config(tmp_path, tmp_path / ".codescope", batch_size=2)
    embedder = FakeEmbedder()

    # Act
    summary = RepositoryIndexer(config, embedder=embedder).rebuild()

    # Assert
    assert [len(batch) for batch in embedder.calls] == [2, 2, 1]
    assert sum(map(len, embedder.calls)) == summary.total_chunks == 5


def test_root_override_returns_result_without_mutating_stored_config(tmp_path: Path) -> None:
    # Arrange
    original = tmp_path / "original"
    override = tmp_path / "override"
    original.mkdir()
    override.mkdir()
    _write(override / "value.py")
    config = _config(original, tmp_path / ".codescope")

    # Act
    summary = RepositoryIndexer(config, embedder=FakeEmbedder()).rebuild(override)

    # Assert
    assert summary.total_files == 1
    assert config.index.root == original.resolve()


def test_progress_stage_order_is_deterministic_and_paths_are_relative(tmp_path: Path) -> None:
    # Arrange
    _write(tmp_path / "value.py")
    _write(tmp_path / "notes.txt", "not source\n")
    events: list[ProgressEvent] = []
    config = _config(tmp_path, tmp_path / ".codescope")

    # Act
    RepositoryIndexer(config, embedder=FakeEmbedder(), progress=events.append).rebuild()

    # Assert
    stages = [event.stage for event in events]
    assert stages[0] == "scan"
    assert stages[-3:] == ["verify", "promote", "complete"]
    assert all(event.file is None or not Path(event.file).is_absolute() for event in events)


def test_expected_parse_failure_skips_file_without_blocking_valid_source(tmp_path: Path) -> None:
    # Arrange
    _write(tmp_path / "bad.py", "BAD = 1\n")
    _write(tmp_path / "good.py", "GOOD = 1\n")

    class SelectiveParser:
        def parse(self, source: bytes, *, file: str, language: str) -> list[Symbol]:
            if file == "bad.py":
                raise ParseFailedError("Safe parse failure.")
            return CodeParser().parse(source, file=file, language=language)

    config = _config(tmp_path, tmp_path / ".codescope")

    # Act
    summary = RepositoryIndexer(
        config,
        parser=SelectiveParser(),  # type: ignore[arg-type]
        embedder=FakeEmbedder(),
    ).rebuild()

    # Assert
    assert summary.total_files == 1
    assert summary.skipped_files >= 1


def test_unexpected_parser_failure_aborts_and_preserves_previous_live_index(
    tmp_path: Path,
) -> None:
    # Arrange
    _write(tmp_path / "value.py")
    runtime = tmp_path / ".codescope"
    config = _config(tmp_path, runtime)
    healthy = RepositoryIndexer(config, embedder=FakeEmbedder())
    healthy.rebuild()
    previous = healthy.status()

    class BrokenParser:
        def parse(self, *_args: object, **_kwargs: object) -> list[Symbol]:
            raise AssertionError("programming defect")

    # Act and Assert
    with pytest.raises(AssertionError, match="programming defect"):
        RepositoryIndexer(
            config,
            parser=BrokenParser(),  # type: ignore[arg-type]
            embedder=FakeEmbedder(),
        ).rebuild()
    assert healthy.status().total_chunks == previous.total_chunks


def test_embedding_failure_cleans_build_directory_and_preserves_previous_index(
    tmp_path: Path,
) -> None:
    # Arrange
    _write(tmp_path / "value.py")
    runtime = tmp_path / ".codescope"
    config = _config(tmp_path, runtime)
    healthy = RepositoryIndexer(config, embedder=FakeEmbedder())
    healthy.rebuild()
    previous = healthy.status()

    # Act
    with pytest.raises(StorageFailedError) as error_info:
        RepositoryIndexer(config, embedder=FakeEmbedder(fail=True)).rebuild()

    # Assert
    assert str(tmp_path) not in str(error_info.value)
    assert healthy.status().total_chunks == previous.total_chunks
    assert list(tmp_path.glob(".codescope.build-*")) == []


def test_successful_rebuild_replaces_prior_runtime_and_removes_unrelated_marker(
    tmp_path: Path,
) -> None:
    # Arrange
    _write(tmp_path / "value.py")
    runtime = tmp_path / ".codescope"
    config = _config(tmp_path, runtime)
    indexer = RepositoryIndexer(config, embedder=FakeEmbedder())
    indexer.rebuild()
    marker = runtime / "old-marker.txt"
    marker.write_text("old", encoding="utf-8")

    # Act
    second = indexer.rebuild()

    # Assert
    assert second.total_files == 1
    assert not marker.exists()
    assert list(tmp_path.glob(".codescope.backup-*")) == []


def test_configuration_fingerprint_is_deterministic_and_relevant(tmp_path: Path) -> None:
    # Arrange
    first = _config(tmp_path, tmp_path / ".codescope")
    second = _config(tmp_path, tmp_path / "other-runtime")
    changed = _config(tmp_path, tmp_path / ".codescope", follow_symlinks=True)

    # Act and Assert
    assert _configuration_fingerprint(first) == _configuration_fingerprint(second)
    assert _configuration_fingerprint(first) != _configuration_fingerprint(changed)


def test_status_does_not_construct_or_load_embedding_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    _write(tmp_path / "value.py")
    config = _config(tmp_path, tmp_path / ".codescope")
    RepositoryIndexer(config, embedder=FakeEmbedder()).rebuild()

    def reject_model(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("model loaded")

    monkeypatch.setattr(indexer_module, "LocalEmbedder", reject_model)

    # Act and Assert
    assert RepositoryIndexer(config).status().index_exists is True


def test_status_rejects_missing_collection_malformed_metadata_and_count_mismatch(
    tmp_path: Path,
) -> None:
    # Arrange
    runtime = tmp_path / ".codescope"
    config = _config(tmp_path, runtime)
    indexer = RepositoryIndexer(config)

    # Act and Assert: missing
    with pytest.raises(IndexNotFoundError):
        indexer.status()

    # Arrange: healthy then malformed metadata
    _write(tmp_path / "value.py")
    RepositoryIndexer(config, embedder=FakeEmbedder()).rebuild()
    (runtime / "index_meta.json").write_text("{}", encoding="utf-8")
    with pytest.raises(IndexNotFoundError):
        indexer.status()

    # Arrange: rebuild then force metadata count mismatch
    RepositoryIndexer(config, embedder=FakeEmbedder()).rebuild()
    storage = ChromaStorage(config.storage, create=False)
    try:
        metadata = storage.read_index_metadata()
        storage.write_index_metadata(metadata.model_copy(update={"chunk_count": 99}))
    finally:
        storage.close()

    # Act and Assert
    with pytest.raises(IndexNotFoundError):
        indexer.status()


def test_index_metadata_matches_accepted_counts_and_fingerprint(tmp_path: Path) -> None:
    # Arrange
    _write(tmp_path / "value.py")
    config = _config(tmp_path, tmp_path / ".codescope")
    summary = RepositoryIndexer(config, embedder=FakeEmbedder()).rebuild()
    storage = ChromaStorage(config.storage, create=False)

    # Act
    try:
        metadata: IndexMetadata = storage.read_index_metadata()
    finally:
        storage.close()

    # Assert
    assert metadata.file_count == summary.total_files
    assert metadata.symbol_count == summary.total_symbols
    assert metadata.chunk_count == summary.total_chunks
    assert metadata.configuration_fingerprint == _configuration_fingerprint(config)
    assert metadata.index_root == "."


def test_fifo_is_recorded_as_non_regular_when_supported(tmp_path: Path) -> None:
    # Arrange
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO creation is unavailable on this operating system")
    os.mkfifo(tmp_path / "pipe.py")
    config = _config(tmp_path, tmp_path / ".codescope")

    # Act
    result = _scanner(config).discover(tmp_path)

    # Assert
    assert SkippedFile("pipe.py", SkipReason.NOT_REGULAR) in result.skipped
