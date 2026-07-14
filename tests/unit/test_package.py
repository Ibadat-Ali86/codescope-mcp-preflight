"""Tests for the CodeScope package foundation."""

import codescope


def test_package_exposes_expected_version() -> None:
    """The package should expose its initial semantic version."""
    assert codescope.__version__ == "0.1.0"
