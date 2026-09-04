"""Sanity test that the hunter_core package is installed and importable."""

import pytest

import hunter_core


@pytest.mark.unit
def test_version() -> None:
    assert hunter_core.__version__ == "0.0.0"
