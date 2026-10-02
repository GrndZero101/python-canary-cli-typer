"""The package imports and declares its own name. Replace or extend as the product grows."""

import template_dogfood


def test_package_imports_under_its_own_name() -> None:
    assert template_dogfood.__name__ == "template_dogfood"
