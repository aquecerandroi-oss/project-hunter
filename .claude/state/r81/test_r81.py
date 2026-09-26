# R81 — testes sintéticos com valores conhecidos.
# cd .claude/state/r81 && PYTHONPATH=C:/dev/project-hunter uv run --project C:/dev/project-hunter pytest -q test_r81.py -p no:cacheprovider
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from r81 import Trade, comprou_no_topo, covered, first_per_mint, structure

T = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)
S0 = 1000  # slot de criação


def tr(sec_before: float, price: str, slot: int, *, recv_after: float = 0.0, idx: int = 0) -> Trade:
    bt = T - timedelta(seconds=sec_before)
    return Trade(bt, bt + timedelta(seconds=recv_after), slot, (idx, 0, 0, f"s{slot}-{idx}"), Decimal(price))


def base() -> list[Trade]:
    # criação em T−290 s (slot 1000, preço 0,5 — excluído); mínimos por minuto 1,0 < 1,1 < 1,2; última 1,5
    return [
        tr(290, "0.5", S0),
        tr(250, "1.3", 1100),
        tr(170, "1.0", 1200),   # [T−180, T−120)
        tr(110, "1.1", 1300),   # [T−120, T−60)
        tr(70, "1.4", 1350),
        tr(50, "1.2", 1400),    # [T−60, T)
        tr(5, "1.5", 1500),     # última
    ]


def test_known_values() -> None:
    s = structure(base(), T, S0)
    assert s is not None
    assert s.price_t == Decimal("1.5") and s.min5 == Decimal("1.0")
    assert s.dist == pytest.approx(0.5)
    assert s.higher_lows is True
    assert s.breakout is True  # 1,5 > máx(1,3; 1,0; 1,1; 1,4; 1,2)
    assert s.n_window == 6


def test_creation_slot_excluded() -> None:
    s_ex = structure(base(), T, S0)
    s_in = structure(base(), T, None)
    assert s_ex is not None and s_in is not None
    assert s_ex.min5 == Decimal("1.0") and s_in.min5 == Decimal("0.5")
    assert s_in.dist == pytest.approx(2.0)


def test_future_and_boundary_trades_change_nothing() -> None:
    """Anti-antecipação: trocas com block_time ≥ T (inclusive exatamente T) não mudam nada."""
    ref = structure(base(), T, S0)
    later = base() + [tr(0, "0.1", 1600), tr(-1, "9.9", 1700), tr(-30, "0.01", 1800)]
    assert structure(later, T, S0) == ref


def test_changing_a_future_trade_changes_nothing() -> None:
    a = base() + [tr(-10, "0.2", 1600)]
    b = base() + [tr(-10, "50", 1600)]
    assert structure(a, T, S0) == structure(b, T, S0)


def test_window_is_300s() -> None:
    """Uma troca em T−301 s está fora; em T−300 s está dentro."""
    out = base() + [tr(301, "0.01", 900)]
    assert structure(out, T, S0) == structure(base(), T, S0)
    inn = base() + [tr(300, "0.75", 950)]
    s = structure(inn, T, S0)
    assert s is not None and s.min5 == Decimal("0.75")


def test_received_filter() -> None:
    """Com received_before_decision, a última troca recebida depois de T sai (o que a base tinha)."""
    tt = base()[:-1] + [tr(5, "1.5", 1500, recv_after=40)]
    s = structure(tt, T, S0, received_before_decision=True)
    assert s is not None and s.price_t == Decimal("1.2") and s.dist == pytest.approx(0.2)
    assert s.breakout is False
    s_or = structure(tt, T, S0)
    assert s_or is not None and s_or.price_t == Decimal("1.5")


def test_absent_is_none_not_zero() -> None:
    assert structure([], T, S0) is None
    assert structure([tr(400, "1", 1)], T, S0) is None
    assert structure([tr(290, "0.5", S0)], T, S0) is None  # só o slot de criação
    one = structure([tr(10, "2", 5)], T, S0)
    assert one is not None and one.dist == 0.0 and one.higher_lows is None and one.breakout is None


def test_higher_lows_false_and_empty_minute() -> None:
    tt = [tr(170, "1.0", 1), tr(110, "0.9", 2), tr(50, "1.2", 3)]
    s = structure(tt, T, S0)
    assert s is not None and s.higher_lows is False
    tt2 = [tr(170, "1.0", 1), tr(50, "1.2", 3)]  # minuto do meio vazio
    s2 = structure(tt2, T, S0)
    assert s2 is not None and s2.higher_lows is None


def test_breakout_excludes_last_slot_and_equal_is_not_above() -> None:
    tt = [tr(100, "1.5", 1), tr(5, "1.5", 2, idx=0), tr(5, "1.7", 2, idx=1)]
    s = structure(tt, T, S0)
    assert s is not None and s.price_t == Decimal("1.7") and s.breakout is True
    tt2 = [tr(100, "1.5", 1), tr(5, "1.5", 2)]
    s2 = structure(tt2, T, S0)
    assert s2 is not None and s2.breakout is False  # igual não é acima


def test_naive_decision_refused() -> None:
    with pytest.raises(ValueError):
        structure(base(), T.replace(tzinfo=None), S0)


def test_covered() -> None:
    assert covered(T - timedelta(seconds=300), T)
    assert not covered(T - timedelta(seconds=299), T)
    assert not covered(None, T)


def test_first_per_mint() -> None:
    rows = [
        {"mint": "A", "lane": "paper", "decided_at": "2026-09-20T12:00:00+00:00", "entry_at": "", "bet_id": "2"},
        {"mint": "A", "lane": "real", "decided_at": "2026-09-20T12:00:00+00:00", "entry_at": "", "bet_id": "1"},
        {"mint": "A", "lane": "real", "decided_at": "2026-09-20T11:00:00+00:00", "entry_at": "", "bet_id": "0"},
    ]
    (f,) = first_per_mint(rows)
    assert f["bet_id"] == "0"
    (g,) = first_per_mint(rows[:2])
    assert g["lane"] == "real"


def test_comprou_no_topo() -> None:
    real = {"lane": "real", "hw_sol": "0.05", "cost_sol": "0.05", "hw_x": "", "pnl_sol": "-0.01"}
    assert comprou_no_topo(real) is True
    assert comprou_no_topo({**real, "hw_sol": "0.06"}) is False
    assert comprou_no_topo({**real, "pnl_sol": "0.001"}) is False
    paper = {"lane": "paper", "hw_sol": "", "cost_sol": "0.05", "hw_x": "0.98", "pnl_sol": "-0.002"}
    assert comprou_no_topo(paper) is True
    assert comprou_no_topo({**paper, "hw_x": ""}) is None


def test_mill_guard_catches_cheater() -> None:
    """A guarda do moinho recusa um batoteiro que usa trocas depois da decisão (proveniência > T)."""
    from infra.research.guards import LookAheadError
    from mill import build_spec

    rows = []
    for i in range(40):
        t = T + timedelta(minutes=10 * i)
        rows.append({"mint": f"m{i}", "day": "2026-09-20", "hora": f"{i}", "t": t, "as_of": t - timedelta(seconds=1),
                     "computed_at": t, "tape_as_of": t - timedelta(seconds=1), "dist": float(i % 7),
                     "ret": 0.01 * (i % 5 - 2), "pnl_sol": "0.0001"})
    cheat = [dict(r) for r in rows]
    cheat[7]["tape_as_of"] = cheat[7]["as_of"] = cheat[7]["t"] + timedelta(seconds=30)  # usou uma troca que só chegou depois
    from infra.research.protocol import run_hypothesis
    run_hypothesis(build_spec(lambda: rows, threshold=3.0, grid=(2.0, 3.0, 4.0), reps=200))
    with pytest.raises(LookAheadError):
        run_hypothesis(build_spec(lambda: cheat, threshold=3.0, grid=(2.0, 3.0, 4.0), reps=200))
