"""CodeScope command-line interface."""

from __future__ import annotations

import importlib
import json
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import ModuleType, TracebackType
from typing import Annotated, Final, NoReturn, cast

import typer
from rich import box
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TaskID, TextColumn
from rich.table import Table

from codescope import __version__
from codescope.config import AppConfig, load_config
from codescope.engine import QueryEngine
from codescope.exceptions import CodeScopeError, QueryFailedError
from codescope.indexer import IndexSummary, ProgressEvent, RepositoryIndexer
from codescope.models import IndexStatus, SearchResult

_CONFIG_PATH: Final = Path("codescope.toml")
_SERVER_UNAVAILABLE: Final = "The MCP server implementation is not available in this build."
_RESET_CONFIRMATION: Final = "Delete the configured local CodeScope index?"

app = typer.Typer(
    name="codescope",
    help="Local-first repository intelligence for coding-agent preflight.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Run the CodeScope command-line interface."""


def _stdout_console() -> Console:
    return Console(markup=False, highlight=False)


def _stderr_console() -> Console:
    return Console(stderr=True, markup=False, highlight=False)


def _terminal_safe(value: str, *, multiline: bool = False) -> str:
    """Neutralize terminal formatting while optionally preserving source layout."""
    if multiline:
        value = value.replace("\r\n", "\n")
    sanitized: list[str] = []
    for character in value:
        category = unicodedata.category(character)
        if multiline and character in {"\n", "\t"}:
            sanitized.append(character)
        elif category.startswith("C") or category in {"Zl", "Zp"}:
            sanitized.append("�")
        else:
            sanitized.append(character)
    return "".join(sanitized)


def _fail(error: CodeScopeError) -> NoReturn:
    console = _stderr_console()
    console.print(f"Error [{error.code}]: {_terminal_safe(error.message)}")
    console.print(f"Suggestion: {_terminal_safe(error.suggestion)}")
    raise typer.Exit(code=1)


def _format_languages(languages: Mapping[str, int]) -> str:
    return (
        ", ".join(
            f"{_terminal_safe(language)}: {count}" for language, count in sorted(languages.items())
        )
        or "None"
    )


def _format_size(size_bytes: int) -> str:
    units = ("bytes", "KiB", "MiB", "GiB", "TiB")
    amount = float(size_bytes)
    unit = units[0]
    for candidate in units[1:]:
        if amount < 1024.0:
            break
        amount /= 1024.0
        unit = candidate
    if unit == "bytes":
        return f"{size_bytes} bytes"
    return f"{amount:.1f} {unit} ({size_bytes} bytes)"


class _IndexProgress:
    """Render one transient interactive task or one bounded deterministic line."""

    def __init__(self, console: Console) -> None:
        self._console = console
        self._progress: Progress | None = None
        self._task_id: TaskID | None = None
        self._events_seen = False
        self._files = 0
        self._skipped = 0
        self._chunks = 0
        self._verified = False
        self._promoted = False
        self._complete = False

    def __enter__(self) -> _IndexProgress:
        if self._console.is_interactive:
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("{task.description}"),
                console=self._console,
                transient=True,
                redirect_stdout=False,
                redirect_stderr=False,
            )
            self._progress.start()
            self._task_id = self._progress.add_task("Preparing local index", total=None)
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        if self._progress is not None:
            self._progress.stop()
        elif self._events_seen and exception_type is None and self._complete:
            self._console.print(
                "Index progress: "
                f"indexed={self._files}; skipped={self._skipped}; "
                f"embedded_chunks={self._chunks}; verified={self._verified}; "
                f"promoted={self._promoted}; complete={self._complete}."
            )

    def update(self, event: ProgressEvent) -> None:
        """Consume one privacy-safe indexer progress event."""
        self._events_seen = True
        if event.stage == "file":
            self._files += 1
        elif event.stage == "skip":
            self._skipped += 1
        elif event.stage == "batch":
            self._chunks = max(self._chunks, event.current)
        elif event.stage == "verify":
            self._verified = True
        elif event.stage == "promote":
            self._promoted = True
        elif event.stage == "complete":
            self._complete = True
        self._update_interactive_description(event)

    def _update_interactive_description(self, event: ProgressEvent) -> None:
        if self._progress is None or self._task_id is None:
            return
        descriptions = {
            "scan": "Scanning repository",
            "skip": f"Scanning repository • skipped {self._skipped}",
            "file": f"Indexing files • accepted {self._files}",
            "batch": f"Embedding chunks • stored {self._chunks}",
            "verify": "Verifying completed index",
            "promote": "Promoting completed index",
            "complete": "Indexing complete",
        }
        self._progress.update(self._task_id, description=descriptions[event.stage])


def _summary_table(summary: IndexSummary) -> Table:
    table = Table(title="CodeScope Index Summary", box=box.SIMPLE, show_header=False)
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("Root", _terminal_safe(summary.root))
    table.add_row("Accepted files", str(summary.total_files))
    table.add_row("Symbols", str(summary.total_symbols))
    table.add_row("Chunks", str(summary.total_chunks))
    table.add_row("Skipped files", str(summary.skipped_files))
    table.add_row("Languages", _format_languages(summary.language_counts))
    table.add_row("Elapsed", f"{summary.elapsed_seconds:.3f} seconds")
    return table


def _status_table(status: IndexStatus) -> Table:
    table = Table(title="CodeScope Index Status", box=box.SIMPLE, show_header=False)
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("State", "Ready" if status.index_exists else "Missing")
    table.add_row("Root", _terminal_safe(status.index_root or "Not available"))
    table.add_row("Last indexed", _terminal_safe(status.last_indexed or "Not available"))
    table.add_row("Files", str(status.total_files))
    table.add_row("Symbols", str(status.total_symbols))
    table.add_row("Chunks", str(status.total_chunks))
    table.add_row("Languages", _format_languages(status.languages))
    table.add_row("Embedding model", _terminal_safe(status.embedding_model))
    table.add_row("Index size", _format_size(status.index_size_bytes))
    return table


def _render_search_results(console: Console, results: Sequence[SearchResult]) -> None:
    if not results:
        console.print("No matching indexed code was found.")
        return
    for position, result in enumerate(results, start=1):
        table = Table(title=f"Result {position}", box=box.SIMPLE, show_header=False)
        table.add_column("Field", style="bold")
        table.add_column("Value")
        table.add_row("Relevance", f"{result.relevance_score:.4f}")
        table.add_row("Symbol", _terminal_safe(result.symbol or "Module-level code"))
        if result.qualified_name is not None:
            table.add_row("Qualified name", _terminal_safe(result.qualified_name))
        table.add_row("Language", _terminal_safe(result.language))
        table.add_row(
            "Location",
            f"{_terminal_safe(result.file)}:{result.start_line}-{result.end_line}",
        )
        console.print(table)
        console.print("Snippet:", style="bold")
        console.print(_terminal_safe(result.snippet, multiline=True), soft_wrap=True)


def _json_results(results: Sequence[SearchResult]) -> str:
    return json.dumps(
        [result.model_dump(mode="json") for result in results],
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _load_server_module() -> ModuleType:
    try:
        return importlib.import_module("codescope.server")
    except ImportError as error:
        raise QueryFailedError(
            _SERVER_UNAVAILABLE,
            suggestion="Install a build containing the Phase 8 MCP server implementation.",
        ) from error


def _run_stdio_server() -> None:
    module = _load_server_module()
    runner = getattr(module, "run_stdio_server", None)
    if not callable(runner):
        raise QueryFailedError(
            _SERVER_UNAVAILABLE,
            suggestion="Complete Phase 8 before using the stdio MCP server.",
        )
    cast(Callable[[], None], runner)()


@app.command()
def version() -> None:
    """Show the installed CodeScope version."""
    typer.echo(f"CodeScope {__version__}")


@app.command("index")
def index_repository(
    path: Annotated[
        Path | None,
        typer.Argument(help="PATH to a Python repository; omit it to use the configured root."),
    ] = None,
    allow_model_download: Annotated[
        bool,
        typer.Option(
            "--allow-model-download",
            help="Explicitly allow downloading the configured embedding model.",
        ),
    ] = False,
) -> None:
    """Build and safely replace the local CodeScope index."""
    try:
        config = load_config(_CONFIG_PATH)
        console = _stdout_console()
        progress = _IndexProgress(console)
        with progress:
            summary = RepositoryIndexer(config, progress=progress.update).rebuild(
                path,
                allow_model_download=allow_model_download,
            )
    except CodeScopeError as error:
        _fail(error)
    console.print(_summary_table(summary))


@app.command("status")
def index_status() -> None:
    """Validate and display the current local index status."""
    try:
        status = RepositoryIndexer(load_config(_CONFIG_PATH)).status()
    except CodeScopeError as error:
        _fail(error)
    _stdout_console().print(_status_table(status))


@app.command("search")
def search_code(
    query: Annotated[str, typer.Argument(help="QUERY describing code behavior to find.")],
    language: Annotated[
        str | None,
        typer.Option("--language", help="Limit results to the supported Python language."),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option("--limit", help="Maximum results, from 1 to the configured maximum."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a JSON array with no styled terminal output."),
    ] = False,
) -> None:
    """Search the existing local index for relevant source code."""
    try:
        config = load_config(_CONFIG_PATH)
        validated_limit = config.search.default_limit if limit is None else limit
        results = QueryEngine(config).search_code(
            query,
            language=language,
            limit=validated_limit,
        )
    except CodeScopeError as error:
        _fail(error)
    if json_output:
        typer.echo(_json_results(results))
        return
    _render_search_results(_stdout_console(), results)


@app.command("serve")
def serve() -> None:
    """Start the local stdio MCP server when its Phase 8 implementation is available."""
    try:
        _run_stdio_server()
    except CodeScopeError as error:
        _fail(error)


@app.command("reset")
def reset_index(
    yes: Annotated[
        bool,
        typer.Option("--yes", help="Delete the validated local index without prompting."),
    ] = False,
) -> None:
    """Delete only the exact validated local CodeScope runtime."""
    try:
        config: AppConfig = load_config(_CONFIG_PATH)
        if not yes and not typer.confirm(_RESET_CONFIRMATION, default=False, err=True):
            _stderr_console().print("Reset cancelled; no files were changed.")
            raise typer.Exit(code=1)
        RepositoryIndexer(config).reset()
    except CodeScopeError as error:
        _fail(error)
    _stdout_console().print("CodeScope index reset successfully.")


if __name__ == "__main__":
    app()
