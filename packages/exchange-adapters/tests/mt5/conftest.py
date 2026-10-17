"""Fixtures of the MT5 contract suite.

``env`` is parametrized ``fake`` / ``live``. The ``live`` variant (a demo terminal on a Windows
box, run by the Everton in the technical session) is marked ``live`` and skipped unless
``HUNTER_LIVE_TESTS=1`` and ``HUNTER_LIVE_MT5_SYMBOL`` are set; it also refuses to run on any
account that is not DEMO, because the suite sends and cancels orders.

The fake lives with the robot's tests (``services/b3-robot/tests/fakes/mt5_fake.py``); the
directory name has a hyphen, so it is loaded by path as the package ``b3_fakes``.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

from hunter_exchanges.mt5.adapter import Mt5Adapter, Mt5Config
from hunter_exchanges.mt5.models import AccountMode
from hunter_exchanges.mt5.port import Mt5Port

FAKES_DIR = Path(__file__).resolve().parents[4] / "services" / "b3-robot" / "tests" / "fakes"


def load_fakes() -> Any:
    if "b3_fakes" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "b3_fakes", FAKES_DIR / "__init__.py", submodule_search_locations=[str(FAKES_DIR)]
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules["b3_fakes"] = module
        spec.loader.exec_module(module)
    return importlib.import_module("b3_fakes.mt5_fake")


@dataclass
class Env:
    port: Mt5Port
    fake: Any  # the FakeMt5 (untyped: loaded by path), or None on a live terminal
    symbol: str
    tick_size: Decimal
    now: Callable[[], datetime]

    @property
    def is_live(self) -> bool:
        return self.fake is None


async def _build_fake(timeout_s: float = 2.0) -> Env:
    fake = load_fakes().FakeMt5()

    def now() -> datetime:
        return datetime.fromtimestamp(fake.broker.now_ms / 1000, tz=UTC)

    port = Mt5Adapter(fake, config=Mt5Config(ipc_call_timeout_s=timeout_s), clock=now)
    await port.attach()
    spec = await port.symbol_spec(fake.broker.symbol)
    port.pin_spec(await port.read_spec_snapshot(spec.symbol))
    return Env(port, fake, spec.symbol, spec.trade_tick_size, now)


async def _build_live() -> Env:
    if os.environ.get("HUNTER_LIVE_TESTS") != "1" or not os.environ.get("HUNTER_LIVE_MT5_SYMBOL"):
        pytest.skip(
            "set HUNTER_LIVE_TESTS=1 and HUNTER_LIVE_MT5_SYMBOL to run against a demo terminal"
        )
    port = Mt5Adapter.for_real_terminal()
    await port.attach()  # no credentials: the terminal is already logged in
    account = await port.account_info()
    if account.trade_mode is not AccountMode.DEMO:
        await port.shutdown()
        pytest.fail("the MT5 contract suite sends orders; it refuses any account that is not DEMO")
    symbol = os.environ["HUNTER_LIVE_MT5_SYMBOL"]
    spec = await port.symbol_spec(symbol)
    port.pin_spec(await port.read_spec_snapshot(symbol))
    return Env(port, None, symbol, spec.trade_tick_size, lambda: datetime.now(UTC))


@pytest_asyncio.fixture(params=["fake", pytest.param("live", marks=pytest.mark.live)])
async def env(request: pytest.FixtureRequest) -> AsyncIterator[Env]:
    built = await (_build_fake() if request.param == "fake" else _build_live())
    yield built
    if built.fake is not None:
        built.fake.release_hang()
    await built.port.shutdown()


@pytest_asyncio.fixture
async def fake_env() -> AsyncIterator[Env]:
    """Fake-only scenarios: they drive the market, faults and the broker's quirks."""
    built = await _build_fake(timeout_s=0.3)
    yield built
    built.fake.release_hang()
    await built.port.shutdown()
