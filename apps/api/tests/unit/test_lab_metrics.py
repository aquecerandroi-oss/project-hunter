"""Unit tests: the pure ``Decimal`` math behind ``/lab/shadow/summary`` — no
IO, no Postgres. SHADOW-LAB.md §9, contract-S3-lab.md.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_api.repositories.lab_summary import OutcomeRow
from hunter_api.services.lab_summary_metrics import (
    bucket_censored_reason,
    expectancy,
    is_evaluable,
    profit_factor,
    quantize4,
    r_ex_funding_of,
    rate,
    sum_of,
    touch_counts,
)
from hunter_core.domain.enums import OutcomeResult, ShadowTrackingState

pytestmark = pytest.mark.unit

_MARKET = uuid.uuid4()
_AS_OF = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


def _row(
    *,
    tracking_state: ShadowTrackingState = ShadowTrackingState.TERMINAL,
    result: OutcomeResult = OutcomeResult.TARGET,
    no_entry_reason: str | None = None,
    censored_reason: str | None = None,
    entry_ts: datetime | None = None,
    exit_ts: datetime | None = None,
    r_multiple: Decimal | None = None,
    meta: dict[str, object] | None = None,
    decision_at: datetime | None = None,
) -> OutcomeRow:
    return OutcomeRow(
        tracking_state=tracking_state,
        result=result,
        no_entry_reason=no_entry_reason,
        censored_reason=censored_reason,
        entry_ts=entry_ts,
        exit_ts=exit_ts,
        r_multiple=r_multiple,
        meta=meta if meta is not None else {},
        market_id=_MARKET,
        decision_at=decision_at or _AS_OF,
    )


def _matured_meta(entry_bar_open: datetime, horizon_s: int) -> dict[str, object]:
    return {"entry_plan": {"entry_bar_open": entry_bar_open.isoformat()}, "horizon_s": horizon_s}


class TestIsEvaluable:
    def test_true_for_a_matured_terminal_row(self) -> None:
        entry_bar_open = _AS_OF - timedelta(hours=5)
        row = _row(
            exit_ts=_AS_OF - timedelta(hours=1),
            meta=_matured_meta(entry_bar_open, 3600),
        )
        assert is_evaluable(row, _AS_OF) is True

    def test_false_when_not_terminal(self) -> None:
        row = _row(tracking_state=ShadowTrackingState.ACTIVE, exit_ts=None)
        assert is_evaluable(row, _AS_OF) is False

    def test_false_when_horizon_has_not_matured_even_if_already_resolved(self) -> None:
        """Astra, contract review, must-fix 2: a fast stop from a decision whose
        4h horizon has not fully elapsed by ``as_of`` must not enter the
        evaluable population yet — including it would over-represent quick
        outcomes over slower peers still waiting to reach ``expired``.
        """
        entry_bar_open = _AS_OF - timedelta(minutes=30)
        row = _row(
            result=OutcomeResult.STOP,
            exit_ts=_AS_OF - timedelta(minutes=25),
            meta=_matured_meta(entry_bar_open, 4 * 3600),
        )
        assert is_evaluable(row, _AS_OF) is False

    def test_false_when_exit_ts_is_after_as_of(self) -> None:
        entry_bar_open = _AS_OF - timedelta(hours=5)
        row = _row(exit_ts=_AS_OF + timedelta(hours=1), meta=_matured_meta(entry_bar_open, 3600))
        assert is_evaluable(row, _AS_OF) is False

    def test_false_when_meta_lacks_the_entry_plan(self) -> None:
        row = _row(exit_ts=_AS_OF - timedelta(hours=1), meta={})
        assert is_evaluable(row, _AS_OF) is False


class TestBucketCensoredReason:
    @pytest.mark.parametrize(
        ("reason", "bucket"),
        [
            ("blocked:BTCUSDT", "blocked"),
            ("gap:2026-09-06T00:54:00+00:00:failed", "gap:failed"),
            ("gap:2026-09-06T00:54:00+00:00:unregistered", "gap:unregistered"),
            ("gap:2026-09-06T00:54:00+00:00:stalled", "gap:stalled"),
            # local data observed without the third segment (older worker image)
            ("gap:2026-09-06T00:54:00+00:00", "gap:unknown"),
            (None, "other"),
            ("something-unexpected", "other"),
        ],
    )
    def test_buckets(self, reason: str | None, bucket: str) -> None:
        assert bucket_censored_reason(reason) == bucket


class TestRExFundingOf:
    def test_parses_the_canonical_decimal_string(self) -> None:
        row = _row(meta={"r_ex_funding": "0.5866087792007041101407029969"})
        assert r_ex_funding_of(row) == Decimal("0.5866087792007041101407029969")

    def test_none_when_absent(self) -> None:
        assert r_ex_funding_of(_row(meta={})) is None


class TestRate:
    def test_null_with_reason_when_denominator_is_zero(self) -> None:
        result = rate(0, 0, reason_if_empty="no_resolved_touches")
        assert result.value is None
        assert result.reason == "no_resolved_touches"

    def test_quantizes_to_four_places(self) -> None:
        result = rate(2, 3, reason_if_empty="no_sample")
        assert result.value == Decimal("0.6667")
        assert result.reason is None


class TestExpectancy:
    def test_no_sample(self) -> None:
        result = expectancy([])
        assert result.value is None
        assert result.reason == "no_sample"

    def test_mean(self) -> None:
        result = expectancy([Decimal("1"), Decimal("-2"), Decimal("0.5")])
        assert result.value == Decimal("-0.1667")


class TestProfitFactor:
    def test_no_sample(self) -> None:
        result = profit_factor([])
        assert result.value is None
        assert result.reason == "no_sample"
        assert result.sum_positive == Decimal(0)
        assert result.sum_negative_abs == Decimal(0)

    def test_no_losses_is_null_not_zero(self) -> None:
        result = profit_factor([Decimal("1"), Decimal("2")])
        assert result.value is None
        assert result.reason == "no_losses"
        assert result.sum_positive == Decimal("3")
        assert result.sum_negative_abs == Decimal(0)

    def test_only_losses_is_zero_not_null(self) -> None:
        result = profit_factor([Decimal("-1"), Decimal("-2")])
        assert result.value == Decimal("0.0000")
        assert result.reason is None

    def test_normal_case_matches_real_local_data(self) -> None:
        """momentum v2, 2026-09-06 local Postgres: Σ+ 1.2809, Σ-（abs) 5.2068."""
        result = profit_factor([Decimal("1.2809"), Decimal("-5.2068")])
        assert result.reason is None
        assert result.value == quantize4(Decimal("1.2809") / Decimal("5.2068"))
        assert result.sample_size == 2

    def test_a_loss_below_the_presentation_resolution_is_not_dropped(self) -> None:
        """Astra, diff review, must-fix 1: quantizing the sums to 4 places
        before checking for losses made ``-0.00004`` compare equal to zero —
        a real PF of 25000 came back ``null`` with the wrong reason instead.
        """
        result = profit_factor([Decimal("1"), Decimal("-0.00004")])
        assert result.reason is None
        assert result.value == Decimal("25000.0000")

    def test_only_a_sub_resolution_loss_is_a_zero_pf_not_null(self) -> None:
        result = profit_factor([Decimal("-0.00004")])
        assert result.value == Decimal("0.0000")
        assert result.reason is None


class TestSumOf:
    def test_no_sample(self) -> None:
        result = sum_of([])
        assert result.value is None
        assert result.reason == "no_sample"
        assert result.count == 0

    def test_sums_and_counts(self) -> None:
        result = sum_of([Decimal("1.5"), Decimal("-0.5")])
        assert result.value == Decimal("1.0000")
        assert result.count == 2


class TestTouchCounts:
    def test_counts_target_and_stop_only(self) -> None:
        rows = [
            _row(result=OutcomeResult.TARGET),
            _row(result=OutcomeResult.TARGET),
            _row(result=OutcomeResult.STOP),
            _row(result=OutcomeResult.EXPIRED),
            _row(result=OutcomeResult.INVALIDATED),
        ]
        assert touch_counts(rows) == (2, 1)


def test_quantize4_rounds_half_up() -> None:
    assert quantize4(Decimal("0.12345")) == Decimal("0.1235")
