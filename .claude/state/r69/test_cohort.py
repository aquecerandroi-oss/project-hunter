"""Prova de que a coorte do R69 nao muda quando o futuro muda."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from cohort import Row, live_cohort, percentile

T = datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)


def _row(mint: str, as_of_s: int, computed_s: int | None = None, v: int | None = 10) -> Row:
    as_of = T + timedelta(seconds=as_of_s)
    return Row(
        mint=mint,
        as_of=as_of,
        computed_at=as_of if computed_s is None else T + timedelta(seconds=computed_s),
        tape_as_of=as_of,
        values={"buys": None if v is None else Decimal(v)},
    )


BASE = [_row("a", -15, v=5), _row("a", -45, v=4), _row("b", -30, v=20), _row("c", -10, v=5)]


def test_cohort_keeps_latest_row_per_mint() -> None:
    coh = live_cohort(BASE, T)
    assert set(coh) == {"a", "b", "c"}
    assert coh["a"].as_of == T - timedelta(seconds=15)


def test_future_as_of_does_not_change_the_cohort() -> None:
    before = live_cohort(BASE, T)
    after = live_cohort([*BASE, _row("a", +1, v=999), _row("d", +30, v=1)], T)
    assert after == before


def test_row_written_after_the_decision_does_not_change_the_cohort() -> None:
    """as_of anterior a t mas computed_at posterior: preenchimento retroativo."""
    late = _row("d", -20, computed_s=+5, v=1)
    assert live_cohort([*BASE, late], T) == live_cohort(BASE, T)


def test_tape_from_the_future_of_its_own_row_is_dropped() -> None:
    r = _row("d", -20, v=1)
    bad = Row(r.mint, r.as_of, r.computed_at, r.as_of + timedelta(seconds=30), r.values)
    assert live_cohort([*BASE, bad], T) == live_cohort(BASE, T)


def test_rows_older_than_the_window_leave_the_cohort() -> None:
    assert "z" not in live_cohort([*BASE, _row("z", -121, v=1)], T)


def test_percentile_excludes_the_subject_and_splits_ties() -> None:
    coh = live_cohort(BASE, T)
    # sujeito 'a' vale 5; referencia = {b:20, c:5} -> (0 menores + 0.5*1 empate)/2 = 0.25
    assert percentile(coh, "a", "buys") == Decimal("0.25")


def test_percentile_is_indifferent_to_row_order() -> None:
    coh1 = live_cohort(BASE, T)
    coh2 = live_cohort(list(reversed(BASE)), T)
    assert percentile(coh1, "a", "buys") == percentile(coh2, "a", "buys")


def test_all_ties_give_half() -> None:
    rows = [_row(m, -10, v=7) for m in ("a", "b", "c", "d")]
    assert percentile(live_cohort(rows, T), "a", "buys") == Decimal("0.5")


def test_subject_without_value_is_unavailable() -> None:
    rows = [_row("a", -10, v=None), _row("b", -10, v=3)]
    assert percentile(live_cohort(rows, T), "a", "buys") is None


def test_empty_reference_is_unavailable() -> None:
    assert percentile(live_cohort([_row("a", -10, v=3)], T), "a", "buys") is None


def test_conservative_lag_drops_rows_inside_the_lag() -> None:
    coh = live_cohort(BASE, T, lag=timedelta(seconds=20))
    assert "c" not in coh  # c foi observada a -10 s, dentro do atraso de 20 s
    assert coh["a"].as_of == T - timedelta(seconds=45)
