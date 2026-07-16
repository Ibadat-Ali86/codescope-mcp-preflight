"""Unit tests for the complete Phase 7 command-line interface."""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
from typing import ClassVar

import pytest
from typer.testing import CliRunner

import codescope.cli as cli_module
from codescope.cli import app
from codescope.config import (
    AppConfig,
    EmbeddingsConfig,
    IndexConfig,
    SearchConfig,
    ServerConfig,
    StorageConfig,
)
from codescope.exceptions import (
    CodeScopeError,
    IndexNotFoundError,
    InvalidLanguageError,
    InvalidLimitError,
    InvalidQueryError,
    StorageFailedError,
)
from codescope.indexer import IndexSummary, ProgressEvent, SkipReason
from codescope.models import IndexStatus, SearchResult

runner = CliRunner()


def _config(root: Path) -> AppConfig:
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
        storage=StorageConfig(path=root / ".codescope", collection="codescope_chunks"),
        search=SearchConfig(default_limit=5, maximum_limit=20, minimum_query_characters=2),
    )


def _result(
    *,
    file: str = "validators.py",
    symbol: str | None = "validate_email",
    qualified_name: str | None = "validate_email",
    snippet: str = "def validate_email(value: str) -> bool:\n    return '@' in value\n",
    score: float = 0.875,
) -> SearchResult:
    return SearchResult(
        file=file,
        start_line=6,
        end_line=9,
        symbol=symbol,
        qualified_name=qualified_name,
        language="python",
        snippet=snippet,
        relevance_score=score,
    )


class FakeIndexer:
    instances: ClassVar[list[FakeIndexer]] = []
    rebuilt_path: ClassVar[Path | None] = None
    allow_download: ClassVar[bool] = False
    status_error: ClassVar[CodeScopeError | None] = None
    reset_error: ClassVar[CodeScopeError | None] = None
    reset_calls: ClassVar[int] = 0

    def __init__(
        self,
        config: AppConfig,
        *,
        progress: object | None = None,
    ) -> None:
        self.config = config
        self.progress = progress
        type(self).instances.append(self)

    def rebuild(
        self,
        root: Path | None = None,
        *,
        allow_model_download: bool = False,
    ) -> IndexSummary:
        type(self).rebuilt_path = root
        type(self).allow_download = allow_model_download
        if callable(self.progress):
            self.progress(ProgressEvent("scan", 0))
            self.progress(
                ProgressEvent(
                    "skip",
                    1,
                    total=3,
                    file="/private/TOP_SECRET_SOURCE.py",
                    reason=SkipReason.UNREADABLE,
                )
            )
            self.progress(ProgressEvent("file", 1, total=2, file="safe.py"))
            self.progress(ProgressEvent("file", 2, total=2, file="other.py"))
            self.progress(ProgressEvent("batch", 4))
            self.progress(ProgressEvent("verify", 0))
            self.progress(ProgressEvent("promote", 0))
            self.progress(ProgressEvent("complete", 2, total=2))
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
        if self.status_error is not None:
            raise self.status_error
        return IndexStatus(
            index_exists=True,
            index_root=".",
            total_files=3,
            total_chunks=4,
            total_symbols=3,
            languages={"zeta": 1, "python": 2},
            last_indexed="2026-07-16T00:00:00Z",
            index_size_bytes=1024,
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        )

    def reset(self) -> None:
        type(self).reset_calls += 1
        if self.reset_error is not None:
            raise self.reset_error
        self.config.storage.path.rmdir()


class FakeEngine:
    instances: ClassVar[list[FakeEngine]] = []
    results: ClassVar[list[SearchResult]] = [_result()]
    error: ClassVar[CodeScopeError | None] = None

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.calls: list[tuple[str, str | None, int]] = []
        type(self).instances.append(self)

    def search_code(
        self,
        query: str,
        language: str | None = None,
        limit: int = 5,
    ) -> list[SearchResult]:
        self.calls.append((query, language, limit))
        if self.error is not None:
            raise self.error
        if len(query.strip()) < 2:
            raise InvalidQueryError("The query is invalid or outside the safe length bounds.")
        if language is not None and language.strip().casefold() != "python":
            raise InvalidLanguageError("The requested language is not supported.")
        if limit < 1 or limit > self.config.search.maximum_limit:
            raise InvalidLimitError("The result limit is outside the configured range.")
        return list(self.results[:limit])


@pytest.fixture(autouse=True)
def _fake_dependencies(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = _config(tmp_path / "repo")
    load_calls: list[Path] = []

    def fake_load(path: Path) -> AppConfig:
        load_calls.append(path)
        return config

    monkeypatch.setattr(cli_module, "load_config", fake_load)
    monkeypatch.setattr(cli_module, "RepositoryIndexer", FakeIndexer)
    monkeypatch.setattr(cli_module, "QueryEngine", FakeEngine)
    monkeypatch.setattr(cli_module, "_test_load_calls", load_calls, raising=False)
    FakeIndexer.instances = []
    FakeIndexer.rebuilt_path = None
    FakeIndexer.allow_download = False
    FakeIndexer.status_error = None
    FakeIndexer.reset_error = None
    FakeIndexer.reset_calls = 0
    FakeEngine.instances = []
    FakeEngine.results = [_result()]
    FakeEngine.error = None
    monkeypatch.chdir(tmp_path)


def _load_calls() -> list[Path]:
    return cli_module._test_load_calls  # type: ignore[attr-defined, no-any-return]


def test_root_help_lists_exact_supported_command_surface_without_side_effects(
    tmp_path: Path,
) -> None:
    # Arrange and Act
    result = runner.invoke(app, ["--help"])

    # Assert
    assert result.exit_code == 0
    for command in ("version", "index", "status", "search", "serve", "reset"):
        assert command in result.stdout
    for unsupported in ("typescript", "javascript", "remote", "dashboard"):
        assert unsupported not in result.stdout.casefold()
    assert _load_calls() == []
    assert FakeIndexer.instances == []
    assert FakeEngine.instances == []
    assert not (tmp_path / ".codescope").exists()


@pytest.mark.parametrize("command", ["version", "index", "status", "search", "serve", "reset"])
def test_every_command_help_is_successful_lazy_and_descriptive(command: str) -> None:
    # Arrange and Act
    result = runner.invoke(app, [command, "--help"])

    # Assert
    assert result.exit_code == 0
    assert "--help" in result.stdout
    assert _load_calls() == []
    assert FakeIndexer.instances == []
    assert FakeEngine.instances == []


def test_help_explains_every_required_argument_and_option() -> None:
    # Arrange and Act
    outputs = {
        command: runner.invoke(app, [command, "--help"]).stdout
        for command in ("index", "search", "reset")
    }

    # Assert
    assert "PATH" in outputs["index"]
    assert "--allow-model-download" in outputs["index"]
    assert "QUERY" in outputs["search"]
    assert "--language" in outputs["search"]
    assert "--limit" in outputs["search"]
    assert "--json" in outputs["search"]
    assert "--yes" in outputs["reset"]


def test_version_is_exact_and_loads_no_config_index_model_or_storage() -> None:
    # Arrange and Act
    result = runner.invoke(app, ["version"])

    # Assert
    assert result.exit_code == 0
    assert result.stdout == "CodeScope 0.1.0\n"
    assert result.stderr == ""
    assert _load_calls() == []
    assert FakeIndexer.instances == []
    assert FakeEngine.instances == []


def test_index_delegates_optional_path_and_explicit_download_permission() -> None:
    # Arrange and Act
    result = runner.invoke(app, ["index", "sample_repo", "--allow-model-download"])

    # Assert
    assert result.exit_code == 0
    assert FakeIndexer.rebuilt_path == Path("sample_repo")
    assert FakeIndexer.allow_download is True


def test_index_defaults_to_configured_root_and_cache_only_model_use() -> None:
    # Arrange and Act
    result = runner.invoke(app, ["index"])

    # Assert
    assert result.exit_code == 0
    assert FakeIndexer.rebuilt_path is None
    assert FakeIndexer.allow_download is False


def test_index_progress_and_summary_are_bounded_safe_and_deterministic(tmp_path: Path) -> None:
    # Arrange and Act
    result = runner.invoke(app, ["index"])

    # Assert
    assert result.exit_code == 0
    assert "Index progress:" in result.stdout
    assert "indexed=2" in result.stdout
    assert "skipped=1" in result.stdout
    assert "embedded_chunks=4" in result.stdout
    for field in (
        "Root",
        "Accepted files",
        "Symbols",
        "Chunks",
        "Skipped files",
        "Languages",
        "Elapsed",
    ):
        assert field in result.stdout
    assert "TOP_SECRET_SOURCE" not in result.stdout + result.stderr
    assert str(tmp_path) not in result.stdout + result.stderr
    assert "\x1b" not in result.stdout + result.stderr


def test_index_typed_failure_is_stderr_only_and_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    secret = "/private/repository"

    class FailingIndexer(FakeIndexer):
        def rebuild(
            self,
            root: Path | None = None,
            *,
            allow_model_download: bool = False,
        ) -> IndexSummary:
            raise StorageFailedError(
                "Repository indexing could not be completed safely."
            ) from OSError(secret)

    monkeypatch.setattr(cli_module, "RepositoryIndexer", FailingIndexer)

    # Act
    result = runner.invoke(app, ["index"])

    # Assert
    assert result.exit_code == 1
    assert "Error [STORAGE_FAILED]" in result.stderr
    assert "Suggestion:" in result.stderr
    assert result.stdout == ""
    assert secret not in result.stderr


def test_status_table_contains_every_required_field_in_deterministic_order() -> None:
    # Arrange and Act
    result = runner.invoke(app, ["status"])

    # Assert
    assert result.exit_code == 0
    fields = (
        "State",
        "Root",
        "Last indexed",
        "Files",
        "Symbols",
        "Chunks",
        "Languages",
        "Embedding model",
        "Index size",
    )
    assert all(field in result.stdout for field in fields)
    assert result.stdout.index("python: 2") < result.stdout.index("zeta: 1")
    assert "1.0 KiB (1024 bytes)" in result.stdout
    assert "Ready" in result.stdout
    assert " ." in result.stdout
    assert FakeEngine.instances == []


def test_status_missing_index_is_actionable_nonzero_and_path_safe(tmp_path: Path) -> None:
    # Arrange
    FakeIndexer.status_error = IndexNotFoundError("No complete usable CodeScope index exists.")

    # Act
    result = runner.invoke(app, ["status"])

    # Assert
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "Error [INDEX_NOT_FOUND]" in result.stderr
    assert "Build the index" in result.stderr
    assert str(tmp_path) not in result.stderr
    assert FakeEngine.instances == []


def test_search_uses_configured_default_limit_and_preserves_engine_order() -> None:
    # Arrange
    FakeEngine.results = [
        _result(file="first.py", symbol="first", qualified_name="Service.first", score=0.9),
        _result(file="second.py", symbol=None, qualified_name=None, score=0.8),
    ]

    # Act
    result = runner.invoke(app, ["search", "email validation"])

    # Assert
    assert result.exit_code == 0
    assert FakeEngine.instances[0].calls == [("email validation", None, 5)]
    assert result.stdout.index("first.py:6-9") < result.stdout.index("second.py:6-9")
    for value in ("0.9000", "first", "Service.first", "python", "Snippet:"):
        assert value in result.stdout


def test_search_delegates_explicit_language_and_limit_without_download_option() -> None:
    # Arrange and Act
    result = runner.invoke(
        app,
        ["search", "email validation", "--language", "python", "--limit", "1"],
    )

    # Assert
    assert result.exit_code == 0
    assert FakeEngine.instances[0].calls == [("email validation", "python", 1)]
    assert not hasattr(FakeEngine.instances[0], "allow_download")


def test_search_zero_results_is_an_explicit_success() -> None:
    # Arrange
    FakeEngine.results = []

    # Act
    result = runner.invoke(app, ["search", "email validation"])

    # Assert
    assert result.exit_code == 0
    assert result.stdout == "No matching indexed code was found.\n"
    assert result.stderr == ""


def test_search_json_is_valid_exact_unstyled_public_output() -> None:
    # Arrange
    FakeEngine.results = [_result()]

    # Act
    result = runner.invoke(app, ["search", "email validation", "--json"])
    payload = json.loads(result.stdout)

    # Assert
    assert result.exit_code == 0
    assert result.stderr == ""
    assert isinstance(payload, list)
    assert set(payload[0]) == {
        "file",
        "start_line",
        "end_line",
        "symbol",
        "qualified_name",
        "language",
        "snippet",
        "relevance_score",
    }
    assert payload[0]["relevance_score"] == 0.875
    assert "Result" not in result.stdout
    assert "\x1b" not in result.stdout


def test_human_search_disables_markup_and_neutralizes_terminal_controls() -> None:
    # Arrange
    FakeEngine.results = [
        _result(
            symbol="[bold]literal[/bold]",
            snippet="value = '[green]literal[/green]'\n\x1b[31mCONTROL",
        )
    ]

    # Act
    result = runner.invoke(app, ["search", "email validation"])

    # Assert
    assert "[bold]literal[/bold]" in result.stdout
    assert "[green]literal[/green]" in result.stdout
    assert "\x1b" not in result.stdout
    assert "�[31mCONTROL" in result.stdout


def test_terminal_metadata_is_forced_to_one_visual_line_and_bidi_neutralized() -> None:
    # Arrange
    unsafe = "safe.py\n\tFORGED‮.txt.py NEXT"

    # Act
    sanitized = cli_module._terminal_safe(unsafe)

    # Assert
    assert sanitized == "safe.py��FORGED�.txt.py�NEXT"
    assert "\n" not in sanitized
    assert "\t" not in sanitized
    assert "‮" not in sanitized
    assert " " not in sanitized


@pytest.mark.parametrize(
    ("arguments", "expected_code"),
    [
        (["search", "x"], "INVALID_QUERY"),
        (["search", "email validation", "--language", "typescript"], "INVALID_LANGUAGE"),
        (["search", "email validation", "--limit", "0"], "INVALID_LIMIT"),
        (["search", "email validation", "--limit", "21"], "INVALID_LIMIT"),
    ],
)
def test_search_validation_failures_are_typed_and_nonzero(
    arguments: list[str],
    expected_code: str,
) -> None:
    # Arrange and Act
    result = runner.invoke(app, arguments)

    # Assert
    assert result.exit_code == 1
    assert result.stdout == ""
    assert f"Error [{expected_code}]" in result.stderr


def test_search_missing_index_does_not_echo_raw_query_or_absolute_path(tmp_path: Path) -> None:
    # Arrange
    raw_query = "PRIVATE_QUERY_MARKER"
    FakeEngine.error = IndexNotFoundError("No complete usable CodeScope index exists.")

    # Act
    result = runner.invoke(app, ["search", raw_query])

    # Assert
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "INDEX_NOT_FOUND" in result.stderr
    assert raw_query not in result.stderr
    assert str(tmp_path) not in result.stderr


def test_serve_shell_is_lazy_stderr_only_and_phase8_honest() -> None:
    # Arrange and Act
    result = runner.invoke(app, ["serve"])

    # Assert
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "MCP server implementation is not available" in result.stderr
    assert "Phase 8" in result.stderr
    assert _load_calls() == []
    assert FakeIndexer.instances == []
    assert FakeEngine.instances == []


def test_unrelated_commands_and_help_never_dispatch_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    def reject_server_load() -> None:
        raise AssertionError("server imported")

    monkeypatch.setattr(cli_module, "_load_server_module", reject_server_load)

    # Act
    help_result = runner.invoke(app, ["--help"])
    version_result = runner.invoke(app, ["version"])

    # Assert
    assert help_result.exit_code == 0
    assert version_result.exit_code == 0


def test_reset_decline_is_nonzero_and_preserves_every_runtime_file() -> None:
    # Arrange
    runtime = _config(Path.cwd() / "repo").storage.path
    runtime.mkdir()
    marker = runtime / "marker.txt"
    marker.write_text("preserve", encoding="utf-8")

    # Act
    result = runner.invoke(app, ["reset"], input="n\n")

    # Assert
    assert result.exit_code == 1
    assert _RESET_PROMPT_TEXT in result.stderr
    assert "Reset cancelled" in result.stderr
    assert "reset successfully" not in result.stdout
    assert FakeIndexer.reset_calls == 0
    assert marker.read_text(encoding="utf-8") == "preserve"


_RESET_PROMPT_TEXT = "Delete the configured local CodeScope index?"


def test_reset_yes_skips_prompt_deletes_exact_runtime_and_reports_success() -> None:
    # Arrange
    config = _config(Path.cwd() / "repo")
    config.storage.path.mkdir()

    # Act
    result = runner.invoke(app, ["reset", "--yes"])

    # Assert
    assert result.exit_code == 0
    assert _RESET_PROMPT_TEXT not in result.stdout + result.stderr
    assert result.stdout == "CodeScope index reset successfully.\n"
    assert result.stderr == ""
    assert FakeIndexer.reset_calls == 1
    assert not config.storage.path.exists()


def test_reset_typed_failure_is_safe_nonzero_and_does_not_print_path(tmp_path: Path) -> None:
    # Arrange
    FakeIndexer.reset_error = StorageFailedError("The local index could not be reset safely.")

    # Act
    result = runner.invoke(app, ["reset", "--yes"])

    # Assert
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "Error [STORAGE_FAILED]" in result.stderr
    assert str(tmp_path) not in result.stderr
