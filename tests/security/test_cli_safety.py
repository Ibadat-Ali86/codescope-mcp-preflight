"""Security tests for the destructive Phase 7 CLI reset boundary."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

import codescope.cli as cli_module
import codescope.indexer as indexer_module
from codescope.cli import app
from codescope.config import (
    AppConfig,
    EmbeddingsConfig,
    IndexConfig,
    SearchConfig,
    ServerConfig,
    StorageConfig,
)
from codescope.exceptions import IndexNotFoundError, InvalidPathError
from codescope.indexer import RepositoryIndexer, RepositoryScanner
from codescope.models import SearchResult
from codescope.utils.path_guard import validate_reset_target

runner = CliRunner()


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


def _unsafe_runtime(config: AppConfig, runtime: Path) -> AppConfig:
    storage = StorageConfig.model_construct(path=runtime, collection="codescope_chunks")
    return config.model_copy(update={"storage": storage})


def _symlink(link: Path, target: Path, *, directory: bool = True) -> None:
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlink creation unavailable on this operating system: {error}")


def test_reset_deletes_only_exact_runtime_and_preserves_repository_siblings(
    tmp_path: Path,
) -> None:
    # Arrange
    root = tmp_path / "repo"
    runtime = root / ".codescope"
    runtime.mkdir(parents=True)
    (runtime / "chroma").mkdir()
    (runtime / "chroma/index.bin").write_bytes(b"index")
    source = root / "source.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    sibling = root / "keep"
    sibling.mkdir()
    (sibling / "marker.txt").write_text("keep", encoding="utf-8")
    external_cache = tmp_path / "model-cache"
    external_cache.mkdir()
    (external_cache / "weights.bin").write_bytes(b"weights")
    config = _config(root, runtime)

    # Act
    RepositoryIndexer(config).reset()

    # Assert
    assert not runtime.exists()
    assert source.read_text(encoding="utf-8") == "VALUE = 1\n"
    assert (sibling / "marker.txt").read_text(encoding="utf-8") == "keep"
    assert (external_cache / "weights.bin").read_bytes() == b"weights"


def test_missing_runtime_is_actionable_not_found_and_never_created(tmp_path: Path) -> None:
    # Arrange
    root = tmp_path / "repo"
    config = _config(root, root / ".codescope")

    # Act and Assert
    with pytest.raises(IndexNotFoundError, match="exists to reset"):
        RepositoryIndexer(config).reset()
    assert not config.storage.path.exists()


@pytest.mark.parametrize("unsafe_kind", ["root", "outside", "traversal", "file"])
def test_reset_rejects_root_external_traversal_and_regular_file_targets(
    tmp_path: Path,
    unsafe_kind: str,
) -> None:
    # Arrange
    root = tmp_path / "repo"
    safe_runtime = root / ".codescope"
    safe_runtime.mkdir(parents=True)
    config = _config(root, safe_runtime)
    if unsafe_kind == "root":
        unsafe = root
    elif unsafe_kind == "outside":
        unsafe = tmp_path / "outside"
        unsafe.mkdir()
    elif unsafe_kind == "traversal":
        unsafe = root / "nested" / ".." / ".codescope"
    else:
        unsafe = root / "runtime-file"
        unsafe.write_text("do not delete", encoding="utf-8")
    unsafe_config = _unsafe_runtime(config, unsafe)

    # Act and Assert
    with pytest.raises(InvalidPathError):
        RepositoryIndexer(unsafe_config).reset()
    assert root.exists()
    assert safe_runtime.exists()
    if unsafe_kind == "outside":
        assert unsafe.exists()
    if unsafe_kind == "file":
        assert unsafe.read_text(encoding="utf-8") == "do not delete"


@pytest.mark.parametrize("target_kind", ["internal", "external"])
def test_reset_rejects_symlink_runtime_and_preserves_target(
    tmp_path: Path,
    target_kind: str,
) -> None:
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    target = root / "internal" if target_kind == "internal" else tmp_path / "external"
    target.mkdir()
    marker = target / "marker.txt"
    marker.write_text("preserve", encoding="utf-8")
    runtime = root / ".codescope"
    _symlink(runtime, target)
    config = _unsafe_runtime(_config(root, root / "placeholder"), runtime)

    # Act and Assert
    with pytest.raises(InvalidPathError):
        RepositoryIndexer(config).reset()
    assert marker.read_text(encoding="utf-8") == "preserve"


def test_nested_runtime_symlink_is_unlinked_without_following_external_target(
    tmp_path: Path,
) -> None:
    # Arrange
    root = tmp_path / "repo"
    runtime = root / ".codescope"
    runtime.mkdir(parents=True)
    external = tmp_path / "external"
    external.mkdir()
    marker = external / "marker.txt"
    marker.write_text("preserve", encoding="utf-8")
    _symlink(runtime / "external-link", external)
    config = _config(root, runtime)

    # Act
    RepositoryIndexer(config).reset()

    # Assert
    assert not runtime.exists()
    assert marker.read_text(encoding="utf-8") == "preserve"


def test_reset_revalidates_immediately_and_validation_failure_deletes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    root = tmp_path / "repo"
    runtime = root / ".codescope"
    runtime.mkdir(parents=True)
    marker = runtime / "marker.txt"
    marker.write_text("preserve", encoding="utf-8")
    config = _config(root, runtime)
    original = indexer_module.validate_reset_target
    calls = 0

    def fail_second(*args: object, **kwargs: object) -> Path:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise InvalidPathError("The reset target changed during validation.")
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(indexer_module, "validate_reset_target", fail_second)

    # Act and Assert
    with pytest.raises(InvalidPathError):
        RepositoryIndexer(config).reset()
    assert calls == 2
    assert marker.read_text(encoding="utf-8") == "preserve"


def test_reset_target_mismatch_and_runtime_parent_are_rejected(tmp_path: Path) -> None:
    # Arrange
    root = tmp_path / "repo"
    runtime = root / "runtime" / ".codescope"
    runtime.mkdir(parents=True)
    other = root / "other"
    other.mkdir()

    # Act and Assert
    for target in (other, runtime.parent):
        with pytest.raises(InvalidPathError):
            validate_reset_target(
                target,
                repository_root=root,
                configured_runtime_path=runtime,
            )
    assert runtime.exists()
    assert other.exists()


def test_confirmation_decline_causes_no_filesystem_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    root = tmp_path / "repo"
    runtime = root / ".codescope"
    runtime.mkdir(parents=True)
    marker = runtime / "marker.txt"
    marker.write_text("preserve", encoding="utf-8")
    config = _config(root, runtime)
    monkeypatch.setattr(cli_module, "load_config", lambda _path: config)

    # Act
    result = runner.invoke(app, ["reset"], input="n\n")

    # Assert
    assert result.exit_code == 1
    assert marker.read_text(encoding="utf-8") == "preserve"


def test_reset_error_output_contains_no_absolute_or_attacker_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "PRIVATE_ATTACKER_TARGET"
    outside.mkdir()
    config = _unsafe_runtime(_config(root, root / "placeholder"), outside)
    monkeypatch.setattr(cli_module, "load_config", lambda _path: config)

    # Act
    result = runner.invoke(app, ["reset", "--yes"])

    # Assert
    assert result.exit_code == 1
    assert str(tmp_path) not in result.stderr
    assert "PRIVATE_ATTACKER_TARGET" not in result.stderr
    assert outside.exists()


def test_repository_filename_cannot_forge_human_terminal_metadata_but_json_roundtrips(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    root = tmp_path / "repo"
    root.mkdir()
    unsafe_name = "safe.py\nError [INDEX_NOT_FOUND]: forged‮.txt NEXT END.py"
    (root / unsafe_name).write_text("VALUE = 1\n", encoding="utf-8")
    config = _config(root, root / ".codescope")
    scanned = RepositoryScanner(config.index, runtime_path=config.storage.path).discover(root)
    assert [item.relative_path for item in scanned.files] == [unsafe_name]
    result = SearchResult(
        file=unsafe_name,
        start_line=1,
        end_line=1,
        symbol=None,
        qualified_name=None,
        language="python",
        snippet="VALUE = 1\n",
        relevance_score=0.5,
    )

    class FilenameEngine:
        def __init__(self, _config: AppConfig) -> None:
            pass

        def search_code(
            self,
            _query: str,
            language: str | None = None,
            limit: int = 5,
        ) -> list[SearchResult]:
            del language, limit
            return [result]

    monkeypatch.setattr(cli_module, "load_config", lambda _path: config)
    monkeypatch.setattr(cli_module, "QueryEngine", FilenameEngine)

    # Act
    human = runner.invoke(app, ["search", "safe query"])
    machine = runner.invoke(app, ["search", "safe query", "--json"])

    # Assert
    assert human.exit_code == 0
    assert "\nError [INDEX_NOT_FOUND]" not in human.stdout
    assert "‮" not in human.stdout
    assert "safe.py�Error [INDEX_NOT_FOUND]: forged�.txt�NEXT�END.py:1-1" in human.stdout
    assert machine.exit_code == 0
    assert unsafe_name not in machine.stdout
    assert "‮" not in machine.stdout
    assert " " not in machine.stdout
    assert " " not in machine.stdout
    assert "\\u202e" in machine.stdout
    assert "\\u2028" in machine.stdout
    assert "\\u2029" in machine.stdout
    assert json.loads(machine.stdout)[0]["file"] == unsafe_name


def test_junction_runtime_policy_is_explicit_when_platform_support_is_unavailable() -> None:
    # Arrange and Act and Assert
    if os.name != "nt":
        pytest.skip("directory junction creation is unavailable on this operating system")
    pytest.skip("junction creation requires operating-system privileges not assumed by this test")
