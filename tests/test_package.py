"""The package imports and declares its own name. Replace or extend as the product grows."""

import python_canary_cli_typer


def test_package_imports_under_its_own_name() -> None:
    assert python_canary_cli_typer.__name__ == "python_canary_cli_typer"
