# R79 — testes sintéticos com valores esperados conhecidos.
# cd .claude/state/r79 && uv run --project C:/dev/project-hunter pytest -q test_r79.py
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from h017 import classify_decision, pair_rows
from h019 import accel, complete, extremes_idx, first_per_mint, peak_le_cost, tertile_idx
from infra.research.guards import Instants, LookAheadError, assert_observable

T0 = "2026-09-25 10:00:00+00"


def _win(b10: str, b60: str, n10: int = 1, n60: int = 6) -> dict:
    return {
        "10s": {"buy_sol": b10, "buys": n10},
        "30s": {"buy_sol": "0", "buys": 0},
        "60s": {"buy_sol": b60, "buys": n60},
    }


def test_accel_known_values() -> None:
    assert accel(_win("1", "6")) == pytest.approx(1.0)  # ritmo constante
    assert accel(_win("0", "6")) == 0.0  # nada nos últimos 10 s: desacelerou
    assert accel(_win("6", "6")) == pytest.approx(6.0)  # tudo nos últimos 10 s
    assert accel(_win("0.5", "3")) == pytest.approx(1.0)
    assert accel(_win("1", "6", n10=3, n60=6), "buys") == pytest.approx(3.0)


def test_accel_missing_is_none_never_zero() -> None:
    assert accel(None) is None
    assert accel({"10s": {"reason": "window_not_covered"}, "60s": {"buy_sol": "2"}}) is None
    assert accel({"10s": {"buy_sol": "1"}, "60s": {"reason": "window_not_covered"}}) is None
    assert accel(_win("0", "0")) is None


def test_accel_reads_only_the_frozen_windows_not_later_trades() -> None:
    """Anti-antecipação: a variável é função só do derivado congelado no instante da decisão."""
    w = _win("1", "6")
    before = accel(w)
    w_with_future = dict(w, trades_after_decision=[{"side": "buy", "sol": "999"}])
    assert accel(w_with_future) == before


def test_guard_catches_a_feature_computed_after_the_decision() -> None:
    dec = datetime(2026, 9, 25, 10, tzinfo=timezone.utc)
    assert_observable(Instants(as_of=dec, computed_at=dec, tape_as_of=dec - timedelta(seconds=1)), dec, "ok")
    cheat = Instants(as_of=dec, computed_at=dec + timedelta(seconds=30), tape_as_of=dec)  # batoteiro: lê a saída
    with pytest.raises(LookAheadError):
        assert_observable(cheat, dec, "cheat")
    late_trade = Instants(as_of=dec, computed_at=dec, tape_as_of=dec + timedelta(seconds=2))
    with pytest.raises(LookAheadError):
        assert_observable(late_trade, dec, "late")


def _row(**k: object) -> dict:
    base: dict = {
        "lane": "paper", "bet_id": "b", "mint": "M", "features_end_time": T0, "entry_at": T0, "has_tape": True,
        "tape_reason": "", "winj": _win("1", "6"), "gaps": "0", "hw_sol": "", "cost_sol": "0.07", "hw_x": "",
    }
    base.update(k)
    return base


def test_first_per_mint_by_decision_then_real() -> None:
    later = "2026-09-25 10:00:05+00"
    rows = [_row(bet_id="p1"), _row(bet_id="r1", lane="real"), _row(bet_id="p0", features_end_time=later, entry_at=later)]
    assert first_per_mint(rows)[0]["bet_id"] == "r1"
    rows2 = [
        _row(bet_id="late", features_end_time=later, entry_at=later),
        _row(bet_id="early", entry_at="2026-09-25 10:00:40+00"),  # recuo: compra depois, decisão antes
    ]
    assert first_per_mint(rows2)[0]["bet_id"] == "early"


def test_complete_requires_both_windows_and_no_reason() -> None:
    assert complete(_row())
    assert not complete(_row(tape_reason="state_ahead_of_decision"))
    assert not complete(_row(has_tape=False))
    assert not complete(_row(winj={"10s": {"reason": "window_not_covered"}, "60s": {"buy_sol": "1"}}))
    assert complete(_row(gaps="2"))
    assert not complete(_row(gaps="2"), no_gaps=True)


def test_peak_le_cost_real_and_paper() -> None:
    assert peak_le_cost(_row(lane="real", hw_sol="0.069", cost_sol="0.07")) is True
    assert peak_le_cost(_row(lane="real", hw_sol="0.0701", cost_sol="0.07")) is False
    assert peak_le_cost(_row(lane="paper", hw_x="1.0")) is True
    assert peak_le_cost(_row(lane="paper", hw_x="1.03")) is False
    assert peak_le_cost(_row(lane="paper", hw_x="")) is None


def test_tertiles_keep_ties_together() -> None:
    x = np.array([0.0, 0.0, 0.0, 0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
    lo, hi, c1, c2 = tertile_idx(x)
    assert c1 == 0.0 and list(lo) == [0, 1, 2, 3]  # 4 zeros juntos, não 3
    assert list(hi) == [6, 7, 8] and c2 == pytest.approx(2.0 + 1 / 3)  # posição 8·2/3 = 5,33 → 2,33
    lo2, hi2, _, _ = extremes_idx(x, 0.5)
    assert set(lo2).isdisjoint(hi2)


def _arm(**k: str) -> dict:
    base = {
        "mint": "M", "t0": T0, "outcomes": "", "arm_bet": "", "arm_status": "", "arm_pnl": "", "arm_size": "",
        "arm_oq": "", "op_bet": "", "op_status": "", "op_pnl": "", "op_size": "", "op_oq": "",
    }
    base.update(k)
    return base


def test_classify_entered_no_pullback_killed_censored() -> None:
    entered = _arm(arm_bet="x", arm_status="closed", arm_pnl="0.007", arm_size="0.07", arm_oq="measured")
    assert classify_decision(entered) == ("entered", pytest.approx(0.1))
    # uma recusa comum da porta num tique posterior NÃO é desfecho do recuo; o no_pullback depois dela é
    tr = "holders_falling@2026-09-25 10:00:10+00# | no_pullback@2026-09-25 10:01:00+00#1.2"
    assert classify_decision(_arm(outcomes=tr)) == ("no_pullback", 0.0)
    killed = "pullback_killed:creator_sold_during_wait@2026-09-25 10:00:30+00#"
    assert classify_decision(_arm(outcomes=killed)) == ("killed", 0.0)
    assert classify_decision(_arm(outcomes="pullback_censored:feed_lost@2026-09-25 10:01:00+00#"))[0] == "censored"
    assert classify_decision(_arm(outcomes="pullback_dropped_cap@2026-09-25 10:00:01+00#"))[0] == "censored"
    indet = _arm(arm_bet="x", arm_status="closed", arm_pnl="0.001", arm_size="0.07", arm_oq="indeterminate")
    assert classify_decision(indet)[0] == "indeterminate"
    assert classify_decision(_arm(arm_bet="x", arm_status="open"))[0] == "open"
    assert classify_decision(_arm(outcomes="holders_falling@2026-09-25 10:00:10+00#"))[0] == "no_outcome"


def test_pairs_zero_for_no_pullback_and_out_without_control() -> None:
    rows = [
        _arm(mint="A", arm_bet="a", arm_status="closed", arm_pnl="0.007", arm_size="0.07",
             op_bet="o", op_status="closed", op_pnl="-0.007", op_size="0.07"),
        _arm(mint="B", outcomes="no_pullback@2026-09-25 10:01:00+00#1",
             op_bet="o", op_status="closed", op_pnl="0.0105", op_size="0.07"),
        _arm(mint="C", arm_bet="c", arm_status="closed", arm_pnl="0.007", arm_size="0.07"),  # sem controle
    ]
    pairs, why = pair_rows(rows)
    got = [(p["mint"], round(p["ra"], 6), round(p["rc"], 6)) for p in pairs]
    assert got == [("A", 0.1, -0.1), ("B", 0.0, 0.15)]
    assert why["no_control"] == 1


def test_label_order_follows_the_block_and_the_r76_errata() -> None:
    from h019_run import label

    assert label(149, 50, 50, -0.2, -0.3, -0.1, 0.1, True, 3, True).startswith("LIMITE")
    assert label(195, 65, 65, -0.2, -0.3, -0.1, 0.31, True, 3, True).startswith("REFUTA por (c)")
    assert label(195, 65, 65, +0.03, +0.001, +0.06, 0.25, True, 3, True).startswith("REFUTA pelo intervalo")
    assert label(195, 65, 65, -0.08, -0.15, -0.01, 0.25, False, 3, True).startswith("REFUTA por (b)")
    assert label(195, 65, 65, -0.08, -0.15, -0.01, 0.25, True, 1.6, True) == "CONFIRMA"
    assert label(195, 65, 65, -0.08, -0.15, -0.01, 0.25, True, 1.2, True).startswith("NÃO CONFIRMA")
    assert label(195, 65, 65, -0.03, -0.10, +0.04, 0.25, True, 3, True).startswith("NÃO CONFIRMA ((a)")
