"""CodeScope command-line interface."""

from pathlib import Path
from typing import Annotated

import typer

from codescope import __version__
from codescope.config import load_config
from codescope.exceptions import CodeScopeError
from codescope.indexer import ProgressEvent, RepositoryIndexer

app = typer.Typer(
    name="codescope",
    help="Local-first repository intelligence for coding-agent preflight.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Run the CodeScope command-line interface."""


@app.command()
def version() -> None:
    """Show the installed CodeScope version."""
    typer.echo(f"CodeScope {__version__}")


def _fail(error: CodeScopeError) -> None:
    typer.echo(f"Error [{error.code}]: {error.message}", err=True)
    typer.echo(f"Suggestion: {error.suggestion}", err=True)
    raise typer.Exit(code=1)


def _progress(event: ProgressEvent) -> None:
    if event.stage == "file" and event.file is not None:
        typer.echo(f"Indexed {event.current}/{event.total}: {event.file}")
    elif event.stage == "skip" and event.file is not None and event.reason is not None:
        typer.echo(f"Skipped {event.file}: {event.reason.value}")


@app.command("index")
def index_repository(
    path: Annotated[Path | None, typer.Argument(help="Repository root override.")] = None,
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
        config = load_config(Path("codescope.toml"))
        summary = RepositoryIndexer(config, progress=_progress).rebuild(
            path,
            allow_model_download=allow_model_download,
        )
    except CodeScopeError as error:
        _fail(error)
    typer.echo(
        "Index complete: "
        f"{summary.total_files} files, {summary.total_symbols} symbols, "
        f"{summary.total_chunks} chunks, {summary.skipped_files} skipped, "
        f"{summary.elapsed_seconds:.3f}s"
    )


@app.command("status")
def index_status() -> None:
    """Validate and display the current local index status."""
    try:
        status = RepositoryIndexer(load_config(Path("codescope.toml"))).status()
    except CodeScopeError as error:
        _fail(error)
    typer.echo(f"Index root: {status.index_root}")
    typer.echo(
        f"Files: {status.total_files} | Symbols: {status.total_symbols} | "
        f"Chunks: {status.total_chunks}"
    )
    typer.echo(f"Languages: {dict(status.languages)}")
    typer.echo(f"Embedding model: {status.embedding_model}")
    typer.echo(f"Last indexed: {status.last_indexed}")
    typer.echo(f"Index size: {status.index_size_bytes} bytes")


if __name__ == "__main__":
    app()
