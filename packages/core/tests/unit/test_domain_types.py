"""Unit tests for hunter_core.domain.types."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from hunter_core.domain.types import ensure_utc, quantize, to_money, utcnow, uuid7


@pytest.mark.unit
def test_to_money_accepts_str_int_decimal() -> None:
    assert to_money("1.50") == Decimal("1.50")
    assert to_money(3) == Decimal(3)
    assert to_money(Decimal("2.5")) == Decimal("2.5")


@pytest.mark.unit
def test_to_money_rejects_float() -> None:
    with pytest.raises(TypeError):
        to_money(1.5)  # type: ignore[arg-type]


@pytest.mark.unit
def test_to_money_rejects_bool() -> None:
    with pytest.raises(TypeError):
        to_money(True)  # type: ignore[arg-type]


@pytest.mark.unit
def test_quantize_rounds_down_to_step() -> None:
    assert quantize(Decimal("1.2345"), Decimal("0.01")) == Decimal("1.23")
    assert quantize(Decimal("1.229"), Decimal("0.01")) == Decimal("1.22")


@pytest.mark.unit
def test_quantize_rejects_non_positive_step() -> None:
    with pytest.raises(ValueError, match="positive"):
        quantize(Decimal("1"), Decimal("0"))


@pytest.mark.unit
def test_utcnow_is_tz_aware_utc() -> None:
    now = utcnow()
    assert now.tzinfo is not None
    assert now.utcoffset() == UTC.utcoffset(now)


@pytest.mark.unit
def test_ensure_utc_rejects_naive_datetime() -> None:
    naive = datetime(2026, 1, 1)  # noqa: DTZ001 - intentionally naive for the test
    with pytest.raises(ValueError, match="naive"):
        ensure_utc(naive)


@pytest.mark.unit
def test_ensure_utc_converts_aware_datetime_to_utc() -> None:
    aware = datetime(2026, 1, 1, tzinfo=UTC)
    assert ensure_utc(aware) == aware


@pytest.mark.unit
def test_uuid7_is_version_7() -> None:
    generated = uuid7()
    assert generated.version == 7
    assert uuid7() != generated
