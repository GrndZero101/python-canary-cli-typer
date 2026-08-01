"""Tests for how the entry point handles missing required arguments.

A subcommand invoked without a required argument shows its full `--help` text
instead of click's terse "Error: Missing argument" line, so a user who is unsure
of a subcommand's shape gets the same answer whether they type nothing or ask
explicitly. A command whose arguments are all defaulted is unaffected, since it
never raises the underlying `MissingParameter` error in the first place.
"""

import pytest

from template_dogfood.cli import main


def test_bare_subcommand_shows_full_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["currency"]) == 0
    captured = capsys.readouterr().out
    assert "Convert an amount between currencies" in captured
    assert "amount to convert" in captured
    assert "currency pair" in captured


def test_bare_subcommand_help_matches_explicit_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main(["currency"])
    bare = capsys.readouterr().out
    main(["currency", "--help"])
    explicit = capsys.readouterr().out
    assert bare == explicit


def test_partial_arguments_also_show_full_help(capsys: pytest.CaptureFixture[str]) -> None:
    """One of two required arguments given is still an omission, not a full call."""
    assert main(["currency", "1000"]) == 0
    assert "currency pair" in capsys.readouterr().out


def test_unknown_subcommand_is_still_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    """A typo in the subcommand name is a different failure than a missing argument."""
    assert main(["bogus"]) == 2
    assert "Error" in capsys.readouterr().err
