"""Unit tests: ``services/regime.py``'s hourly-engine detection, the
``regime_hourly_v1`` staleness rule (T3.43b) and the ``supporting_features``
decomposition it exposes on ``RegimeOut`` -- no IO, no Redis, no DB.

``HOURLY_FEATURES`` mirrors the real persisted shape byte for byte: every
number a canonical decimal *string* (never a JSON number), the same fields
``services/scanner-worker/tests/test_regime_job.py
::test_the_row_carries_the_whole_decomposition`` asserts against and
``.claude/state/notes-T3.43.md`` documents -- not a shape invented for this
test file.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_api.repositories.regime import RegimeRow
from hunter_api.schemas.regime import RegimeComponentOut
from hunter_api.services.regime import (
    HOURLY_ENGINE_VERSION_PREFIX,
    HOURLY_STALE_AFTER,
    _components,  # pyright: ignore[reportPrivateUsage]
    _decimal,  # pyright: ignore[reportPrivateUsage]
    _hourly_is_stale,  # pyright: ignore[reportPrivateUsage]
    _is_hourly_engine,  # pyright: ignore[reportPrivateUsage]
    _to_out,  # pyright: ignore[reportPrivateUsage]
    build_current,
    is_regime_hourly_fresh,
)
from hunter_core.domain.enums import MarketRegime, RegimeScope
from hunter_core.domain.types import utcnow

pytestmark = pytest.mark.unit

HOURLY_FEATURES: dict[str, Any] = {
    "engine": "regime_hourly",
    "version": "regime_hourly_v1",
    "ts": "2026-09-08T15:00:00Z",
    "trend": "up",
    "vol_regime": "normal",
    "breadth_pct": "54.32",
    "funding_avg": "0.00008",
    "drawdown_pct": "3.10",
    "score_0_100": "62.00",
    "confidence": "0.8000",
    "regime": "BTC_BULL",
    "components": [
        {
            "name": "trend",
            "raw": "0.004",
            "normalized": "100",
            "weight": "0.35",
            "contribution": "35.00",
            "reason": None,
        },
        {
            "name": "breadth",
            "raw": "54.32",
            "normalized": "54.32",
            "weight": "0.25",
            "contribution": "13.58",
            "reason": None,
        },
        {
            "name": "volatility",
            "raw": "40",
            "normalized": "60",
            "weight": "0.20",
            "contribution": "12.00",
            "reason": None,
        },
        {
            "name": "drawdown",
            "raw": "3.10",
            "normalized": "84.50",
            "weight": "0.10",
            "contribution": "8.45",
            "reason": None,
        },
        {
            "name": "funding",
            "raw": "0.00008",
            "normalized": None,
            "weight": "0.10",
            "contribution": None,
            "reason": "funding_unavailable",
        },
    ],
    "inputs": {"closes": 745},
    "reasons": [],
}

HOUR = timedelta(hours=1)


def _row(
    *,
    start_time: datetime,
    end_time: datetime | None,
    classifier_version: str | None,
    supporting_features: dict[str, Any] | None = None,
    scope: RegimeScope = RegimeScope.BTC,
) -> RegimeRow:
    return RegimeRow(
        id=uuid.uuid4(),
        scope=scope,
        regime=MarketRegime.BTC_BULL,
        confidence=Decimal("0.8000"),
        start_time=start_time,
        end_time=end_time,
        classifier_version=classifier_version,
        supporting_features=supporting_features if supporting_features is not None else {},
    )


def _hourly_row(*, end_time: datetime, classifier_version: str = "regime_hourly_v1") -> RegimeRow:
    return _row(
        start_time=end_time - HOUR,
        end_time=end_time,
        classifier_version=classifier_version,
        supporting_features=dict(HOURLY_FEATURES),
    )


class TestIsHourlyEngine:
    def test_exact_version_is_hourly(self) -> None:
        row = _hourly_row(end_time=utcnow())
        assert _is_hourly_engine(row) is True

    def test_digest_suffixed_version_is_hourly(self) -> None:
        """``HourlyThresholds.identity`` folds an override into
        ``regime_hourly_v1+<digest>`` -- a prefix match, not an exact one."""
        row = _hourly_row(end_time=utcnow(), classifier_version="regime_hourly_v1+abc123def456")
        assert _is_hourly_engine(row) is True

    def test_regime_v0_is_not_hourly(self) -> None:
        row = _row(start_time=utcnow() - HOUR, end_time=utcnow(), classifier_version="regime_v0")
        assert _is_hourly_engine(row) is False

    def test_none_classifier_version_is_not_hourly(self) -> None:
        row = _row(start_time=utcnow() - HOUR, end_time=None, classifier_version=None)
        assert _is_hourly_engine(row) is False

    def test_unrelated_prefix_is_not_hourly(self) -> None:
        """``regime_hourly_v2`` (a hypothetical future engine) must not match
        ``regime_hourly_v1``'s prefix -- ``HOURLY_ENGINE_VERSION_PREFIX``
        itself includes the trailing digit."""
        assert HOURLY_ENGINE_VERSION_PREFIX == "regime_hourly_v1"
        row = _row(
            start_time=utcnow() - HOUR, end_time=utcnow(), classifier_version="regime_hourly_v2"
        )
        assert _is_hourly_engine(row) is False


class TestIsRegimeHourlyFresh:
    def test_none_reads_not_fresh(self) -> None:
        """No ``hb:scanner:*`` heartbeat ever carried ``regime_last_ts`` (or
        Redis could not be read) -- fail safe, never assume fresh."""
        assert is_regime_hourly_fresh(None) is False

    def test_recent_heartbeat_is_fresh(self) -> None:
        assert is_regime_hourly_fresh(datetime.now(UTC) - timedelta(minutes=5)) is True

    def test_heartbeat_just_inside_the_boundary_is_fresh(self) -> None:
        # Not "exactly at": ``utcnow()`` inside the function runs microseconds
        # after this line, so an exact boundary flips with the clock (flaky
        # under load, seen 2026-09-08). One second inside is the honest edge.
        assert (
            is_regime_hourly_fresh(datetime.now(UTC) - HOURLY_STALE_AFTER + timedelta(seconds=1))
            is True
        )

    def test_heartbeat_past_two_hours_is_not_fresh(self) -> None:
        assert (
            is_regime_hourly_fresh(datetime.now(UTC) - HOURLY_STALE_AFTER - timedelta(seconds=1))
            is False
        )


class TestHourlyIsStale:
    def test_recent_hour_with_fresh_heartbeat_is_not_stale(self) -> None:
        row = _hourly_row(end_time=utcnow() - timedelta(minutes=10))
        assert _hourly_is_stale(row, regime_hourly_fresh=True) is False

    def test_recent_hour_without_a_fresh_heartbeat_is_stale(self) -> None:
        """A closed-but-young row still reads stale when nothing confirms the
        producer is still writing -- the row's own age is not, by itself,
        proof the pipeline is alive."""
        row = _hourly_row(end_time=utcnow() - timedelta(minutes=10))
        assert _hourly_is_stale(row, regime_hourly_fresh=False) is True

    def test_hour_older_than_two_hours_is_stale_even_with_a_fresh_heartbeat(self) -> None:
        """The hour itself has aged out -- a live producer three hours later
        does not make *this* hour current again."""
        row = _hourly_row(end_time=utcnow() - HOURLY_STALE_AFTER - timedelta(minutes=1))
        assert _hourly_is_stale(row, regime_hourly_fresh=True) is True

    def test_hour_exactly_at_the_two_hour_boundary_is_not_stale_by_age(self) -> None:
        row = _hourly_row(end_time=utcnow() - HOURLY_STALE_AFTER)
        assert _hourly_is_stale(row, regime_hourly_fresh=True) is False


class TestDecimalParsing:
    def test_none_stays_none(self) -> None:
        assert _decimal(None) is None

    def test_decimal_string_parses_exactly(self) -> None:
        assert _decimal("62.00") == Decimal("62.00")

    def test_a_decimal_passes_through(self) -> None:
        assert _decimal(Decimal("0.8000")) == Decimal("0.8000")

    def test_garbage_reads_none_not_a_500(self) -> None:
        assert _decimal("not-a-number") is None


class TestComponentsParsing:
    def test_well_formed_list_keeps_only_the_four_fields(self) -> None:
        components = _components(HOURLY_FEATURES["components"])
        assert len(components) == 5
        assert components[0] == RegimeComponentOut(
            name="trend",
            normalized=Decimal("100"),
            weight=Decimal("0.35"),
            contribution=Decimal("35.00"),
        )
        # `raw`/`reason` are in `supporting_features` still, not duplicated here.
        assert not hasattr(components[0], "raw")
        assert not hasattr(components[0], "reason")

    def test_a_missing_component_stays_none_not_zero(self) -> None:
        """The funding component with no usable input (``normalized``/
        ``contribution`` both ``null``) must read ``None``, never a
        fabricated ``0`` standing in for "no signal"."""
        components = _components(HOURLY_FEATURES["components"])
        funding = next(c for c in components if c.name == "funding")
        assert funding.normalized is None
        assert funding.contribution is None
        assert funding.weight == Decimal("0.10")

    def test_not_a_list_returns_empty(self) -> None:
        assert _components(None) == []
        assert _components("regime_hourly") == []
        assert _components({"name": "trend"}) == []

    def test_entry_missing_name_or_weight_is_dropped(self) -> None:
        assert _components([{"normalized": "10"}]) == []
        assert _components([{"name": "trend"}]) == []
        assert _components(["not-a-dict"]) == []


class TestToOut:
    def test_non_hourly_row_gets_none_for_every_new_field(self) -> None:
        row = _row(
            start_time=utcnow() - timedelta(days=3650),
            end_time=utcnow() - timedelta(days=3650) + HOUR,
            classifier_version=None,
            scope=RegimeScope.GLOBAL,
        )
        out = _to_out(row, scanner_alive=True, regime_hourly_fresh=True)
        assert out.as_of is None
        assert out.score is None
        assert out.components == []
        assert out.identity is None
        # regime_v0's own rule is untouched: closed -> stale, scanner heartbeat aside.
        assert out.is_stale is True

    def test_non_hourly_open_row_with_alive_scanner_is_not_stale(self) -> None:
        row = _row(
            start_time=utcnow(), end_time=None, classifier_version=None, scope=RegimeScope.GLOBAL
        )
        out = _to_out(row, scanner_alive=True, regime_hourly_fresh=False)
        assert out.is_stale is False

    def test_hourly_row_exposes_the_decomposition(self) -> None:
        end_time = utcnow() - timedelta(minutes=10)
        row = _hourly_row(end_time=end_time)
        out = _to_out(row, scanner_alive=False, regime_hourly_fresh=True)
        assert out.as_of == row.start_time
        assert out.score == Decimal("62.00")
        assert out.identity == "regime_hourly_v1"
        assert [c.name for c in out.components] == [
            "trend",
            "breadth",
            "volatility",
            "drawdown",
            "funding",
        ]
        # regime_v0's `scanner_alive` must play no role for an hourly row.
        assert out.is_stale is False

    def test_hourly_row_with_no_score_reads_none_not_fabricated(self) -> None:
        row = _hourly_row(end_time=utcnow())
        row.supporting_features["score_0_100"] = None
        out = _to_out(row, scanner_alive=True, regime_hourly_fresh=True)
        assert out.score is None


class TestBuildCurrent:
    def test_mixed_scopes_each_apply_their_own_rule(self) -> None:
        stale_v0 = _row(
            start_time=utcnow() - timedelta(days=3650),
            end_time=utcnow() - timedelta(days=3650) + HOUR,
            classifier_version=None,
            scope=RegimeScope.GLOBAL,
        )
        fresh_hourly = _hourly_row(end_time=utcnow() - timedelta(minutes=5))
        result = build_current(
            [stale_v0, fresh_hourly], scanner_alive=False, regime_hourly_fresh=True
        )
        by_scope = {item.scope: item for item in result.items}
        assert by_scope[RegimeScope.GLOBAL].is_stale is True
        assert by_scope[RegimeScope.BTC].is_stale is False
        assert by_scope[RegimeScope.BTC].score == Decimal("62.00")
        assert by_scope[RegimeScope.GLOBAL].score is None
