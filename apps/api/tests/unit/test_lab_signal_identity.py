"""``compute_identity_key`` (T3.38a) -- the stable hash of "same operation"
across sibling strategy versions: same market + same decision bar + same
entry/exit prices + same exit reason + same result. Brief:
``.claude/state/brief-T3.38-lab-identical-signals-grouped.md`` item 2.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from hunter_api.services.lab_signal_identity import compute_identity_key
from hunter_core.domain.enums import OutcomeResult

BAR_CLOSE = datetime(2026, 9, 8, 15, 0, tzinfo=UTC)


def _key(**overrides: object) -> str:
    base: dict[str, object] = {
        "market": "RAYSOLUSDT",
        "source_bar_close": BAR_CLOSE,
        "entry_price": Decimal("1.16930116"),
        "exit_price": Decimal("1.1865126569"),
        "exit_reason": "target",
        "result": OutcomeResult.TARGET,
    }
    base.update(overrides)
    return compute_identity_key(**base)  # type: ignore[arg-type]


def test_identical_inputs_produce_the_same_key() -> None:
    assert _key() == _key()


def test_it_is_a_stable_deterministic_hash_not_a_random_id() -> None:
    first = _key()
    second = _key()
    assert first == second
    # sha256 hex digest -- 64 lowercase hex chars, not a uuid or a counter.
    assert len(first) == 64
    assert all(c in "0123456789abcdef" for c in first)


def test_a_different_exit_price_is_a_different_operation() -> None:
    assert _key(exit_price=Decimal("1.1865126570")) != _key()


def test_a_different_entry_price_is_a_different_operation() -> None:
    assert _key(entry_price=Decimal("1.16930117")) != _key()


def test_a_different_market_is_a_different_operation() -> None:
    assert _key(market="BTCUSDT") != _key()


def test_a_different_source_bar_close_is_a_different_operation() -> None:
    other = datetime(2026, 9, 8, 15, 15, tzinfo=UTC)
    assert _key(source_bar_close=other) != _key()


def test_a_different_exit_reason_is_a_different_operation() -> None:
    assert _key(exit_reason="stop") != _key()


def test_a_different_result_is_a_different_operation() -> None:
    assert _key(result=OutcomeResult.STOP) != _key()


def test_a_naive_source_bar_close_datetime_is_rejected() -> None:
    import pytest

    with pytest.raises(ValueError):
        _key(source_bar_close=datetime(2026, 9, 8, 15, 0))  # noqa: DTZ001


def test_none_prices_and_none_reason_do_not_collapse_into_the_same_key_as_zero_or_empty() -> None:
    """A missing entry price (never entered) must not hash identically to a
    concrete ``0`` entry price, and a missing exit reason must not collide
    with the empty string -- distinct concepts, distinct keys.
    """
    none_entry = _key(entry_price=None)
    zero_entry = _key(entry_price=Decimal("0"))
    assert none_entry != zero_entry

    none_reason = _key(exit_reason=None)
    empty_reason = _key(exit_reason="")
    assert none_reason != empty_reason
