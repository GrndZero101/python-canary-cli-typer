"""Single entry point mounting every subcommand.

    tdf-cli geo cleve
    tdf-cli currency 1000 GBP/AUD --margin 2.5
    tdf-cli weather cleve

Named `tdf-cli`, not `cli` — on Windows PowerShell, `cli` is a built-in alias for
`Clear-Item`, so an installed script by that name would silently lose to the alias
unless invoked with an extension or full path.

Each subcommand lives in its own module and is registered here as a plain function, not with
its own nested `typer.Typer`. Registration by reference keeps `tdf-cli geo …` two words instead
of three, and keeps `geo` importable and callable on its own — from a test, from pdb, or from a
debugger's evaluate-expression prompt with literal arguments.

`add_completion=False` is deliberate. Typer's `--install-completion` rewrites `~/.zshrc` with
no backup, never consults `$ZDOTDIR`, and appends an unconditional `compinit`. Emit the script
instead and let the user or packager place it:

    _TDF_CLI_COMPLETE=source_zsh tdf-cli > "${ZDOTDIR:-$HOME}/completions/_tdf-cli"

Note `source_zsh`, not `zsh_source` — typer inverts Click 8's order for backwards compatibility.
Typer derives the completion env var by uppercasing `prog_name` and replacing `-` with `_`, so
the hyphen in `tdf-cli` becomes a valid `_TDF_CLI_COMPLETE`.
"""

import sys

import typer

from .currency import currency
from .geo import geo
from .typer_entrypoint import run_app
from .weather import weather

app = typer.Typer(add_completion=False, no_args_is_help=True)
app.command("geo")(geo)
app.command("currency")(currency)
app.command("weather")(weather)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an exit code; never calls sys.exit itself."""
    return run_app(app, argv, prog_name="tdf-cli")


if __name__ == "__main__":
    sys.exit(main())
