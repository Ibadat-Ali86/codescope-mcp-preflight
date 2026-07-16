"""Tests for the narrow Phase 5 command-line bridge."""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import ClassVar

import pytest
from typer.testing import CliRunner

import codescope.cli as cli_module
from codescope.cli import app
from codescope.exceptions import IndexNotFoundError
from codescope.indexer import IndexSummary
from codescope.models import IndexStatus

runner = CliRunner()


class FakeIndexer:
    rebuilt_path: ClassVar[Path | None] = None
    allow_download: ClassVar[bool] = False

    def __init__(self, _config: object, *, progress: object | None = None) -> None:
        self.progress = progress

    def rebuild(
        self,
        root: Path | None = None,
        *,
        allow_model_download: bool = False,
    ) -> IndexSummary:
        type(self).rebuilt_path = root
        type(self).allow_download = allow_model_download
        return IndexSummary(
            root=".",
            total_files=2,
            total_symbols=3,
            total_chunks=4,
            skipped_files=1,
            language_counts=MappingProxyType({"python": 2}),
            elapsed_seconds=0.125,
        )

    def status(self) -> IndexStatus:
        return IndexStatus(
            index_exists=True,
            index_root=".",
            total_files=2,
            total_chunks=4,
            total_symbols=3,
            languages={"python": 2},
            last_indexed="2026-07-15T00:00:00Z",
            index_size_bytes=1024,
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        )


@pytest.fixture(autouse=True)
def _fake_dependencies(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli_module, "load_config", lambda _path: object())
    monkeypatch.setattr(cli_module, "RepositoryIndexer", FakeIndexer)
    FakeIndexer.rebuilt_path = None
    FakeIndexer.allow_download = False
    monkeypatch.chdir(tmp_path)


def test_version_command_remains_available() -> None:
    # Arrange and Act
    result = runner.invoke(app, ["version"])

    # Assert
    assert result.exit_code == 0
    assert result.stdout == "CodeScope 0.1.0\n"


def test_index_command_delegates_path_and_explicit_download_permission() -> None:
    # Arrange and Act
    result = runner.invoke(
        app,
        ["index", "sample_repo", "--allow-model-download"],
    )

    # Assert
    assert result.exit_code == 0
    assert FakeIndexer.rebuilt_path == Path("sample_repo")
    assert FakeIndexer.allow_download is True
    assert "2 files, 3 symbols, 4 chunks, 1 skipped, 0.125s" in result.stdout


def test_index_command_defaults_to_cache_only_and_configured_root() -> None:
    # Arrange and Act
    result = runner.invoke(app, ["index"])

    # Assert
    assert result.exit_code == 0
    assert FakeIndexer.rebuilt_path is None
    assert FakeIndexer.allow_download is False


def test_status_command_displays_only_bounded_relative_information() -> None:
    # Arrange and Act
    result = runner.invoke(app, ["status"])

    # Assert
    assert result.exit_code == 0
    assert "Index root: ." in result.stdout
    assert "Files: 2 | Symbols: 3 | Chunks: 4" in result.stdout
    assert "/home/" not in result.stdout
    assert "C:\\" not in result.stdout


def test_status_missing_index_exits_nonzero_with_actionable_safe_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Arrange
    class MissingIndexer(FakeIndexer):
        def status(self) -> IndexStatus:
            raise IndexNotFoundError("No complete usable CodeScope index exists.")

    monkeypatch.setattr(cli_module, "RepositoryIndexer", MissingIndexer)

    # Act
    result = runner.invoke(app, ["status"])

    # Assert
    assert result.exit_code == 1
    assert "INDEX_NOT_FOUND" in result.stderr
    assert "Build the index" in result.stderr
    assert str(tmp_path) not in result.stdout + result.stderr


def test_phase5_cli_does_not_add_search_serve_or_reset_commands() -> None:
    # Arrange and Act
    result = runner.invoke(app, ["--help"])

    # Assert
    assert result.exit_code == 0
    assert "index" in result.stdout
    assert "status" in result.stdout
    assert "version" in result.stdout
    assert "search" not in result.stdout
    assert "serve" not in result.stdout
    assert "reset" not in result.stdout
