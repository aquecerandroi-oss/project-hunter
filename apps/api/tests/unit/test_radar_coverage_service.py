"""Unit tests: ``services/radar_coverage.py``'s pure helpers -- heartbeat
field parsing, the gate-percentage arithmetic and the always-twelve
detectors list. No IO, no Redis, no DB (T3.46, ``.claude/state/notes-T3.46
.md``).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from hunter_api.repositories.radar_coverage import BaselineGateProgress
from hunter_api.services.radar_coverage import (
    _parse_disarmed,  # pyright: ignore[reportPrivateUsage]
    _parse_int,  # pyright: ignore[reportPrivateUsage]
    build_detectors,
    gate_pct,
)
from hunter_core.domain.enums import AnomalyType

pytestmark = pytest.mark.unit


def test_parse_int_valid() -> None:
    assert _parse_int("9029") == 9029


def test_parse_int_none_or_missing_is_zero() -> None:
    assert _parse_int(None) == 0
    assert _parse_int("") == 0


def test_parse_int_garbage_is_zero_not_a_raise() -> None:
    assert _parse_int("not-a-number") == 0


def test_parse_disarmed_the_real_heartbeat_shape() -> None:
    raw = (
        "CROSS_EXCHANGE_DIVERGENCE:single_exchange_until_m1b=200,"
        "FUNDING_ANOMALY:funding_unavailable=200,"
        "LIQUIDATION_CLUSTER:feature_not_implemented=200"
    )
    parsed = _parse_disarmed(raw)
    assert parsed == {
        AnomalyType.CROSS_EXCHANGE_DIVERGENCE: "single_exchange_until_m1b",
        AnomalyType.FUNDING_ANOMALY: "funding_unavailable",
        AnomalyType.LIQUIDATION_CLUSTER: "feature_not_implemented",
    }


def test_parse_disarmed_empty_or_none_is_empty_dict() -> None:
    assert _parse_disarmed(None) == {}
    assert _parse_disarmed("") == {}


def test_parse_disarmed_drops_an_unknown_type_rather_than_raising() -> None:
    """A future detector name the enum has not caught up with yet must not 500 the page."""
    parsed = _parse_disarmed("SOME_FUTURE_TYPE:some_reason=5,VOLUME_SPIKE:warmup=1")
    assert parsed == {AnomalyType.VOLUME_SPIKE: "warmup"}


def test_gate_pct_none_when_no_progress() -> None:
    assert gate_pct(None) is None


def test_gate_pct_none_when_total_is_zero() -> None:
    """No baseline row exists yet -- ``None``, never a fabricated 0%."""
    assert gate_pct(BaselineGateProgress(passing=0, total=0, gate_version="v2")) is None


def test_gate_pct_matches_the_real_t346_reading() -> None:
    """11754 / 274596 -- the exact T3.46 inventory reading (4.28 %)."""
    progress = BaselineGateProgress(passing=11754, total=274596, gate_version="v2")
    assert gate_pct(progress) == Decimal("4.28")


def test_build_detectors_always_returns_all_twelve_members() -> None:
    detectors = build_detectors({}, {})
    assert len(detectors) == len(AnomalyType)
    assert {d.type for d in detectors} == set(AnomalyType)


def test_build_detectors_producing_wins_even_with_a_stale_disarmed_reason() -> None:
    detectors = build_detectors(
        {AnomalyType.VOLUME_SPIKE: 575}, {AnomalyType.VOLUME_SPIKE: "warmup"}
    )
    row = next(d for d in detectors if d.type == AnomalyType.VOLUME_SPIKE)
    assert row.rows_31d == 575
    assert row.disarmed_reason == "warmup"


def test_build_detectors_silent_with_no_rows_and_no_declared_reason() -> None:
    """The T3.46 defect: zero rows, no reason in `detectors_disarmed`."""
    detectors = build_detectors({}, {})
    row = next(d for d in detectors if d.type == AnomalyType.ORDERBOOK_IMBALANCE)
    assert row.rows_31d == 0
    assert row.disarmed_reason is None
