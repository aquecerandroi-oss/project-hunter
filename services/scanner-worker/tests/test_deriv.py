"""Derivative history, and the two detectors that are mute without it.

``open_interest_change_1h/4h`` and ``funding_change_8h`` read ``deriv_history``,
which is **not** in the hot state: the ``deriv`` hash carries the current value
only, so "change since the first reading this process saw" would be a statement
about the process, not about the market (notes-T2.2 section 8). Until T2.5b the
loader existed (``repo.load_deriv_history``) and nobody called it, so
``OPEN_INTEREST_SPIKE`` was armed and permanently silent — the exact shape the
brief refuses: never armed and mute.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest
from sqlalchemy import insert

from hunter_core.db.models.market_data import OpenInterestHistory
from hunter_core.db.session import role_session
from hunter_core.domain.enums import AnomalyType
from hunter_indicators.anomalies import (
    DEFAULT_DETECTORS,
    DetectorDefinition,
    evaluate_detector,
)
from hunter_indicators.anomalies.detectors import REASON_DISABLED
from hunter_indicators.baselines import BaselineCut, BaselineProjection
from hunter_indicators.features import Quality, build_context, compute_features
from hunter_indicators.features.hotstate import decode_deriv
from hunter_scanner_worker.deriv import (
    REASON_NO_FUNDING,
    REASON_NO_OI_HISTORY,
    DerivHistory,
    detector_roster,
    history_entry,
)
from hunter_scanner_worker.registry import MarketRef

from .builders import EXCHANGE, MARKET_ID, SYMBOL, deriv_hash, series
from .db_helpers import seed_market
from .policies import build_policy

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


def _by_type(roster: tuple[DetectorDefinition, ...], kind: AnomalyType) -> DetectorDefinition:
    return next(item for item in roster if item.type is kind)


def test_without_open_interest_history_the_spike_detector_is_disarmed_with_a_reason() -> None:
    roster = detector_roster(has_oi_history=False, has_funding=True)

    definition = _by_type(roster, AnomalyType.OPEN_INTEREST_SPIKE)
    assert definition.enabled is False
    assert definition.disabled_reason == REASON_NO_OI_HISTORY


def test_without_a_funding_reading_the_funding_detector_is_disarmed_with_a_reason() -> None:
    roster = detector_roster(has_oi_history=True, has_funding=False)

    definition = _by_type(roster, AnomalyType.FUNDING_ANOMALY)
    assert definition.enabled is False
    assert definition.disabled_reason == REASON_NO_FUNDING


def test_a_disarmed_detector_says_so_in_its_evaluation_instead_of_staying_quiet() -> None:
    definition = _by_type(
        detector_roster(has_oi_history=False, has_funding=True),
        AnomalyType.OPEN_INTEREST_SPIKE,
    )
    candles = series(120)
    vector = compute_features(
        build_context(
            exchange=EXCHANGE,
            symbol=SYMBOL,
            as_of=candles[-1].close_time,
            candles=candles,
        )
    ).vector

    evaluation = evaluate_detector(
        definition,
        market_id=MARKET_ID,
        vector=vector,
        projection=BaselineProjection(
            (),
            cut=BaselineCut(as_of=vector.ts, observation_ts=vector.ts),
            gate=build_policy().gate,
        ),
        config=build_policy().normalization,
    )

    assert evaluation.reason == REASON_DISABLED
    assert evaluation.detail == REASON_NO_OI_HISTORY


def test_the_roster_rearms_as_soon_as_the_history_is_there() -> None:
    disarmed = detector_roster(has_oi_history=False, has_funding=False)
    armed = detector_roster(has_oi_history=True, has_funding=True)

    assert _by_type(disarmed, AnomalyType.OPEN_INTEREST_SPIKE).enabled is False
    assert _by_type(disarmed, AnomalyType.FUNDING_ANOMALY).enabled is False
    assert _by_type(armed, AnomalyType.OPEN_INTEREST_SPIKE).enabled is True
    assert _by_type(armed, AnomalyType.FUNDING_ANOMALY).enabled is True
    # Everything else is the shipped roster, untouched.
    assert len(armed) == len(DEFAULT_DETECTORS)
    assert armed == DEFAULT_DETECTORS


async def _seed_oi(factory: Any, market_id: Any, stamps: list[datetime]) -> None:
    rows = [
        {
            "market_id": market_id,
            "ts": stamp,
            "open_interest": Decimal("1000") + Decimal(index),
            "open_interest_value": None,
        }
        for index, stamp in enumerate(stamps)
    ]
    async with role_session(factory, db_role="hunter_worker") as session:
        await session.execute(insert(OpenInterestHistory).values(rows))


@pytest.mark.integration
async def test_the_history_of_open_interest_makes_the_change_features_computable(
    db_session_factory: Any,
) -> None:
    symbol = "OIHIST1USDT"
    market_id = await seed_market(db_session_factory, EXCHANGE, symbol)
    await _seed_oi(
        db_session_factory,
        market_id,
        [NOW - timedelta(minutes=minute) for minute in range(0, 9 * 60 + 5, 5)],
    )
    ref = MarketRef(market_id=market_id, exchange=EXCHANGE, symbol=symbol)

    history = DerivHistory()
    loaded = await history.refresh(db_session_factory, [ref], now=NOW)

    assert loaded > 0, "the loader has to be called for real, not left unwired"
    observations = history.for_market(market_id)
    # The window must reach past the longest lookback that reads it
    # (``funding_change_8h``: 8 h plus 48 min of tolerance), or the feature is
    # warm-up forever.
    assert (observations[-1].ts - observations[0].ts) >= timedelta(hours=8, minutes=48)

    # The candles are the builders' (``BTCUSDT``): the context is keyed by
    # exchange/symbol and the history by ``market_id``, and this test is about
    # the second one.
    candles = series(1500, start=NOW - timedelta(minutes=1500))
    vector = compute_features(
        build_context(
            exchange=EXCHANGE,
            symbol=SYMBOL,
            as_of=NOW,
            candles=candles,
            deriv=decode_deriv(cast("dict[str | bytes, str | bytes]", deriv_hash(ts=NOW)), NOW),
            deriv_history=history_entry(observations, NOW),
        )
    ).vector

    for key in ("open_interest_change_1h", "open_interest_change_4h"):
        assert vector.values[key].quality is Quality.OK, vector.values[key].reason


@pytest.mark.integration
async def test_the_incremental_reload_still_sees_a_row_inserted_behind_the_cursor(
    db_session_factory: Any,
) -> None:
    symbol = "OIHIST2USDT"
    market_id = await seed_market(db_session_factory, EXCHANGE, symbol)
    ref = MarketRef(market_id=market_id, exchange=EXCHANGE, symbol=symbol)
    await _seed_oi(db_session_factory, market_id, [NOW - timedelta(minutes=20)])

    history = DerivHistory()
    await history.refresh(db_session_factory, [ref], now=NOW)

    # The late sample is stamped **older** than the newest one already held, which
    # is the only case a cursor placed after the newest reading would miss: the
    # query filters on the observation's own ``ts``, not on insertion order.
    late = NOW - timedelta(minutes=25)
    await _seed_oi(db_session_factory, market_id, [late])
    await history.refresh(db_session_factory, [ref], now=NOW + timedelta(minutes=1))

    stamps = [observation.ts for observation in history.for_market(market_id)]
    assert late in stamps, "a cursor after the newest reading loses rows inserted late"
    assert NOW - timedelta(minutes=20) in stamps
    assert len(stamps) == len(set(stamps)), "the overlap must not duplicate readings"
    assert stamps == sorted(stamps)
