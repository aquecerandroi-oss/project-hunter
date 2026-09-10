"""``build_family_readers`` — grouping, ceiling and failure isolation (T3.74b).

Unit, no database: :func:`hunter_strategy_worker.replay.candles.load_window` is
monkeypatched, so what is proved here is the *arithmetic* around it (which
members share a reader, which ceiling they share it at, and that one family's
failure never reaches another's or the caller's). The reader's own correctness
(byte-identical to ``load_candles``) is already proved by
``test_replay_engine.py::TestTheCandleCache`` — reused, not re-proved.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from hunter_core.strategies.canonical import params_hash
from hunter_core.strategies.mean_reversion_v1 import MEAN_REVERSION_V1
from hunter_core.strategies.volume_anomaly_v1 import VOLUME_ANOMALY_V1
from hunter_strategy_worker import context_cache
from hunter_strategy_worker.catalogue import ActiveVersion
from hunter_strategy_worker.config import ShadowConfig

pytestmark = pytest.mark.unit

BAR_CLOSE = datetime(2026, 9, 10, 5, 45, tzinfo=UTC)
CONFIG = ShadowConfig()
MARKET: Any = object()
"""Never touched: ``load_window`` is monkeypatched, so nothing here ever reads
a real ``MarketRow``."""
SESSION: Any = object()


def _version(strategy: Any, key: str, *, params: dict[str, Any] | None = None) -> ActiveVersion:
    frozen = dict(params or strategy.default_parameters)
    return ActiveVersion(
        id=uuid.uuid4(),
        strategy_key=key,
        version="v1",
        params=frozen,
        params_hash=params_hash(frozen),
        strategy=strategy,
        code_ref=None,
        purpose="research_only",
    )


def _fake_load_window(
    calls: list[dict[str, Any]], *, fail_for: frozenset[int] = frozenset()
) -> Any:
    """A stand-in for ``load_window`` that records every call and can fail for
    specific ``context_minutes`` ceilings, to prove isolation without a real
    ``WindowCache``."""

    async def fake(
        session: Any,
        *,
        market: Any,
        window_start: datetime,
        window_end: datetime,
        context_minutes: int,
    ) -> Any:
        calls.append(
            {
                "market": market,
                "window_start": window_start,
                "window_end": window_end,
                "context_minutes": context_minutes,
            }
        )
        if context_minutes in fail_for:
            raise RuntimeError("preload failed")
        return f"cache:{context_minutes}"

    return fake


class TestGrouping:
    async def test_a_lone_version_gets_no_reader(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[dict[str, Any]] = []
        monkeypatch.setattr(context_cache, "load_window", _fake_load_window(calls))
        version = _version(VOLUME_ANOMALY_V1, "volume_anomaly")
        readers = await context_cache.build_family_readers(
            SESSION, [version], market=MARKET, bar_close=BAR_CLOSE, config=CONFIG
        )
        assert readers == {}
        assert calls == []

    async def test_two_versions_of_one_family_share_one_reader(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[dict[str, Any]] = []
        monkeypatch.setattr(context_cache, "load_window", _fake_load_window(calls))
        a = _version(VOLUME_ANOMALY_V1, "volume_anomaly")
        b = _version(VOLUME_ANOMALY_V1, "volume_anomaly")
        readers = await context_cache.build_family_readers(
            SESSION, [a, b], market=MARKET, bar_close=BAR_CLOSE, config=CONFIG
        )
        assert set(readers) == {"volume_anomaly"}
        assert len(calls) == 1, "one preload for the whole family, not one per member"
        assert calls[0]["window_start"] == calls[0]["window_end"] == BAR_CLOSE

    async def test_two_families_never_share_a_reader(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[dict[str, Any]] = []
        monkeypatch.setattr(context_cache, "load_window", _fake_load_window(calls))
        versions = [
            _version(VOLUME_ANOMALY_V1, "volume_anomaly"),
            _version(VOLUME_ANOMALY_V1, "volume_anomaly"),
            _version(MEAN_REVERSION_V1, "mean_reversion"),
            _version(MEAN_REVERSION_V1, "mean_reversion"),
        ]
        readers = await context_cache.build_family_readers(
            SESSION, versions, market=MARKET, bar_close=BAR_CLOSE, config=CONFIG
        )
        assert set(readers) == {"volume_anomaly", "mean_reversion"}
        assert len(calls) == 2

    async def test_a_family_due_only_once_this_bar_gets_no_reader(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``versions`` is the ``due`` list for *this* bar close, not the whole
        roster — a family with three live siblings but only one aligned this
        bar must not be treated as shared."""
        calls: list[dict[str, Any]] = []
        monkeypatch.setattr(context_cache, "load_window", _fake_load_window(calls))
        due_this_bar = [_version(VOLUME_ANOMALY_V1, "volume_anomaly")]
        readers = await context_cache.build_family_readers(
            SESSION, due_this_bar, market=MARKET, bar_close=BAR_CLOSE, config=CONFIG
        )
        assert readers == {}


class TestCeiling:
    async def test_the_ceiling_is_the_widest_members_requirement(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[dict[str, Any]] = []
        monkeypatch.setattr(context_cache, "load_window", _fake_load_window(calls))
        narrow = _version(MEAN_REVERSION_V1, "mean_reversion")
        wide_params = dict(MEAN_REVERSION_V1.default_parameters)
        wide_params["trend_sma_bars"] = wide_params["trend_sma_bars"] * 4
        wide = _version(MEAN_REVERSION_V1, "mean_reversion", params=wide_params)
        assert narrow.context_minutes(CONFIG) < wide.context_minutes(CONFIG), (
            "the fixture must actually produce two different requirements"
        )
        readers = await context_cache.build_family_readers(
            SESSION, [narrow, wide], market=MARKET, bar_close=BAR_CLOSE, config=CONFIG
        )
        assert len(calls) == 1
        assert calls[0]["context_minutes"] == wide.context_minutes(CONFIG)
        assert readers["mean_reversion"] == f"cache:{wide.context_minutes(CONFIG)}"


class TestFailureIsolation:
    async def test_a_failed_preload_yields_no_reader_for_that_family_only(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        volume = [_version(VOLUME_ANOMALY_V1, "volume_anomaly") for _ in range(2)]
        # A different, wider ceiling than volume's — both default to the same
        # 1560 floor otherwise, and the fake below fails *by ceiling*, so the
        # two families need distinguishable ones for this test to mean anything.
        wide_params = dict(MEAN_REVERSION_V1.default_parameters)
        wide_params["trend_sma_bars"] = wide_params["trend_sma_bars"] * 4
        reversion = [
            _version(MEAN_REVERSION_V1, "mean_reversion", params=wide_params) for _ in range(2)
        ]
        assert volume[0].context_minutes(CONFIG) != reversion[0].context_minutes(CONFIG)
        ceiling = volume[0].context_minutes(CONFIG)
        calls: list[dict[str, Any]] = []
        monkeypatch.setattr(
            context_cache, "load_window", _fake_load_window(calls, fail_for=frozenset({ceiling}))
        )
        readers = await context_cache.build_family_readers(
            SESSION, volume + reversion, market=MARKET, bar_close=BAR_CLOSE, config=CONFIG
        )
        assert "volume_anomaly" not in readers, "the family whose preload failed gets no reader"
        assert "mean_reversion" in readers, (
            "a sibling family's cache must not be taken down with it"
        )
        assert len(calls) == 2, "both families were attempted"
