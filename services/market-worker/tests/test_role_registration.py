"""Importing ``hunter_market_worker`` registers the ``market`` role."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_market_role_registered_after_import() -> None:
    import hunter_market_worker
    from hunter_core.runtime import RoleRegistry
    from hunter_market_worker.main import run_market

    assert RoleRegistry["market"] is run_market
    assert hunter_market_worker.__version__
