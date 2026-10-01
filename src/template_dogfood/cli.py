"""Single entry point: the app, its global options, and every subcommand.

    tdf-cli about
    tdf-cli -v about --output json
    TDF_CLI_OUTPUT=json tdf-cli about
    tdf-cli weather cleve

`about` is a placeholder. Add a command by writing it in its own module as a plain function and
registering it here by reference, not with its own nested `typer.Typer`. That keeps
`tdf-cli <command>` two words instead of three, and keeps the function importable and
callable on its own — from a test, from pdb, or from a debugger's evaluate-expression prompt.

The script is deliberately not called `cli`. On Windows, `cli` is a read-only PowerShell alias
for `Clear-Item`, and an alias beats an executable on PATH — so a command by that name is
unreachable from the shell most Windows users are in.

`add_completion=False` is deliberate. Typer's `--install-completion` rewrites `~/.zshrc` with
no backup, never consults `$ZDOTDIR`, and appends an unconditional `compinit`. Emit the script
instead and let the user or packager place it:

    _TDF_CLI_COMPLETE=source_zsh tdf-cli > "${ZDOTDIR:-$HOME}/completions/_tdf-cli"

Note `source_zsh`, not `zsh_source` — typer inverts Click 8's order for backwards compatibility.
"""

import sys

import typer

from .about import about_command
from .config import PROG_NAME, SettingsError, load_settings
from .logging_setup import configure_logging
from .options import GlobalOptions, VerboseOption, VersionOption
from .typer_entrypoint import run_app
from .weather import weather

USAGE_ERROR = 2

app = typer.Typer(add_completion=False, no_args_is_help=True)
app.command("about")(about_command)
app.command("weather")(weather)


@app.callback()
def configure(
    ctx: typer.Context,
    *,
    verbose: VerboseOption = None,
    # Acted on by its eager callback before this body runs, so it is never read here.
    version: VersionOption = False,  # ruff: ignore[unused-function-argument]
) -> None:
    """Global options go before the command name."""
    settings = load_settings(verbose=verbose)
    configure_logging(verbose=settings.verbose)
    ctx.obj = GlobalOptions(verbose=verbose)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an exit code; never calls sys.exit itself."""
    try:
        return run_app(app, argv, prog_name=PROG_NAME)
    except SettingsError as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return USAGE_ERROR


if __name__ == "__main__":
    sys.exit(main())
