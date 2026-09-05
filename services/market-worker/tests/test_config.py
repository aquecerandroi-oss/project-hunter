"""``config.exchange_code``/``build_adapter`` — docs/plans/M1.md T1.3."""

from __future__ import annotations

import sys
import types

import pytest

from hunter_market_worker.config import (
    DEFAULT_EXCHANGE_CODE,
    UnsupportedExchangeError,
    build_adapter,
    exchange_code,
)

pytestmark = pytest.mark.unit


def test_exchange_code_defaults_to_binance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MARKET_EXCHANGE_CODE", raising=False)
    assert exchange_code() == DEFAULT_EXCHANGE_CODE == "binance"


def test_exchange_code_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKET_EXCHANGE_CODE", "  BINANCE  ")
    assert exchange_code() == "binance"


def test_build_adapter_rejects_unknown_code() -> None:
    with pytest.raises(UnsupportedExchangeError):
        build_adapter("bybit", settings=object(), redis=object())  # type: ignore[arg-type]


def test_build_adapter_reports_missing_binance_package(monkeypatch: pytest.MonkeyPatch) -> None:
    """``hunter_exchanges.binance`` (T1.2) was developed concurrently with this
    task and could be absent or fail to import; a failed import must surface
    as :class:`UnsupportedExchangeError`, never an unhandled ``ImportError``
    deep in a task group. Setting a ``sys.modules`` entry to ``None`` is the
    documented way to force ``import`` to raise ``ImportError`` even though
    the real package is installed."""
    monkeypatch.setitem(sys.modules, "hunter_exchanges.binance", None)
    with pytest.raises(UnsupportedExchangeError, match="not importable"):
        build_adapter("binance", settings=object(), redis=object())  # type: ignore[arg-type]


def test_build_adapter_constructs_the_registered_class(monkeypatch: pytest.MonkeyPatch) -> None:
    """Once ``hunter_exchanges.binance.BinanceAdapter`` exists, ``build_adapter``
    constructs it with a ``rest`` client wired to a Redis-backed rate limiter
    — exercised here with a stand-in module so this test does not depend on
    T1.2's actual classes (only on ``config.py``'s own import path)."""
    rate_limiter_args: dict[str, object] = {}
    created_rest_clients: list[_StubRestClient] = []

    class _StubRateLimiter:
        def __init__(self, exchange: str, *, redis: object) -> None:
            rate_limiter_args.update(exchange=exchange, redis=redis)

    class _StubRestClient:
        def __init__(self, *, rate_limiter: object) -> None:
            self.rate_limiter = rate_limiter
            created_rest_clients.append(self)

    class _StubBinanceAdapter:
        code = "binance"

        def __init__(self, *, rest: object) -> None:
            self.rest = rest

    adapter_module = types.ModuleType("hunter_exchanges.binance")
    adapter_module.BinanceAdapter = _StubBinanceAdapter  # type: ignore[attr-defined]
    rest_module = types.ModuleType("hunter_exchanges.binance.rest")
    rest_module.BinanceRestClient = _StubRestClient  # type: ignore[attr-defined]
    rate_limit_module = types.ModuleType("hunter_exchanges.rate_limit")
    rate_limit_module.TokenBucketRateLimiter = _StubRateLimiter  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "hunter_exchanges.binance", adapter_module)
    monkeypatch.setitem(sys.modules, "hunter_exchanges.binance.rest", rest_module)
    monkeypatch.setitem(sys.modules, "hunter_exchanges.rate_limit", rate_limit_module)

    settings, redis = object(), object()
    adapter = build_adapter("binance", settings=settings, redis=redis)  # type: ignore[arg-type]

    assert isinstance(adapter, _StubBinanceAdapter)
    assert rate_limiter_args == {"exchange": "binance", "redis": redis}
    assert len(created_rest_clients) == 1
    assert isinstance(created_rest_clients[0].rate_limiter, _StubRateLimiter)
    assert adapter.rest is created_rest_clients[0]
