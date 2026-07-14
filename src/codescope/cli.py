"""CodeScope command-line interface."""

import typer

from codescope import __version__

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


if __name__ == "__main__":
    app()
