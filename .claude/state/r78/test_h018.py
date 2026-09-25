# R78 — testes sintéticos da lógica da H-018 (recompra após ganho, controle, contrafactual, concorrência).
# uv run --project C:/dev/project-hunter pytest .claude/state/r78/test_h018.py -q -p no:cacheprovider
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
import pytest

from h018 import Pos, boot_diff, concurrent_pairs, cooldown_counterfactual, first_entries, reentries

T0 = datetime(2026, 9, 24, 7, 0, tzinfo=UTC)


def pos(i, mint, rs, e, x, pnl, size="0.07", origin=None, reason=None):
    return Pos(f"b{i}", mint, rs, T0 + timedelta(seconds=e), T0 + timedelta(seconds=x),
               Decimal(pnl), Decimal(size), reason or ("target" if Decimal(pnl) > 0 else "trailing"),
               f"S{mint}", origin or f"o{i}")


def ids(pairs):
    return [q.bet_id for q, _ in pairs]


def test_megawatt_is_a_cross_reentry_not_a_same_one():
    rows = [pos(1, "M", "op6", 0, 4, "0.016"), pos(2, "M", "op5", 9, 30, "-0.0519")]
    assert ids(reentries(rows, "any")) == ["b2"]
    assert ids(reentries(rows, "cross")) == ["b2"]
    assert reentries(rows, "same") == []


def test_window_is_inclusive_300s_and_needs_a_gain_and_a_closed_prior():
    rows = [
        pos(1, "A", "op5", 0, 10, "0.01"), pos(2, "A", "op5", 310, 320, "-0.01"),  # 300 s exatos: conta
        pos(3, "B", "op5", 0, 10, "0.01"), pos(4, "B", "op5", 311, 320, "-0.01"),  # 301 s: não conta
        pos(5, "C", "op5", 0, 10, "-0.01"), pos(6, "C", "op5", 20, 30, "-0.01"),   # anterior perdeu
        pos(7, "D", "op5", 0, 50, "0.01"), pos(8, "D", "op6", 20, 60, "-0.01"),    # concorrente, não recompra
    ]
    assert ids(reentries(rows, "any")) == ["b2"]


def test_one_reentry_per_prior_exit_and_first_after_it():
    rows = [pos(1, "A", "op5", 0, 10, "0.01"), pos(2, "A", "op5", 20, 30, "-0.01"), pos(3, "A", "op6", 40, 50, "-0.01")]
    assert ids(reentries(rows, "any")) == ["b2"]  # b3 vem depois de uma saída perdedora (b2)


def test_an_intermediate_loss_breaks_the_link_to_an_older_gain():
    # Astra (desenho R78, must-fix 1): ganho t=10, perda t=100, entrada t=150 não é recompra após ganho
    rows = [pos(1, "A", "op5", 0, 10, "0.01"), pos(2, "A", "op6", 5, 100, "-0.01"), pos(3, "A", "op5", 150, 160, "-0.02")]
    assert "b3" not in ids(reentries(rows, "any"))


def test_same_origin_decision_is_not_a_reentry():
    # Astra (must-fix 2): sombra e recuo_v1 da MESMA decisão não são uma recompra
    rows = [pos(1, "A", "operator/5", 0, 10, "0.01", origin="d1"), pos(2, "A", "recuo_v1/1", 20, 30, "-0.01", origin="d1")]
    assert reentries(rows, "any") == []


def test_target_prior_is_the_literal_primary_and_gain_is_the_sensitivity():
    rows = [pos(1, "A", "op5", 0, 10, "0.01", reason="max_hold"), pos(2, "A", "op5", 20, 30, "-0.01")]
    assert reentries(rows, "any", prior="target") == []
    assert ids(reentries(rows, "any", prior="gain")) == ["b2"]


def test_first_entries_by_scope():
    rows = [pos(1, "A", "op5", 0, 10, "0.01"), pos(2, "A", "op6", 20, 30, "0.01"), pos(3, "A", "op5", 40, 50, "0.01")]
    assert [p.bet_id for p in first_entries(rows, "any")] == ["b1"]
    assert [p.bet_id for p in first_entries(rows, "same")] == ["b1", "b2"]


def test_counterfactual_is_sequential_and_any_result():
    rows = [
        pos(1, "A", "op6", 0, 10, "0.01"),     # executa
        pos(2, "A", "op5", 15, 20, "-0.05"),   # bloqueada (5 s depois de b1)
        pos(3, "A", "op5", 400, 420, "0.02"),  # 390 s depois de b1: livre (b2 não existiu)
        pos(4, "B", "op5", 0, 10, "-0.01"),
        pos(5, "B", "op6", 100, 110, "0.03"),  # bloqueada depois de perda (o check 28 já cobria)
    ]
    blocked, delta = cooldown_counterfactual(rows, 300)
    assert [(b.bet_id, prev.bet_id) for b, prev in blocked] == [("b2", "b1"), ("b5", "b4")]
    assert delta == Decimal("0.02")  # −(−0,05 + 0,03)
    blocked_loss, delta_loss = cooldown_counterfactual(rows, 300, trigger="loss")
    assert [b.bet_id for b, _ in blocked_loss] == ["b5"]
    assert delta_loss == Decimal("-0.03")


def test_counterfactual_window_is_exclusive_like_check_28_and_loss_means_negative():
    rows = [pos(1, "A", "op6", 0, 10, "0"), pos(2, "A", "op5", 310, 320, "-0.05"),   # 300 s exatos: livre
            pos(3, "B", "op6", 0, 10, "0"), pos(4, "B", "op5", 20, 30, "-0.05")]     # pnl 0: check 28 não conta
    assert [b.bet_id for b, _ in cooldown_counterfactual(rows, 300)[0]] == ["b4"]
    assert cooldown_counterfactual(rows, 300, trigger="loss")[0] == []


def test_old_policy_block_can_free_a_later_trade():
    # Astra (must-fix 4): replays com estados próprios
    rows = [pos(1, "A", "op6", 0, 0, "0.01"), pos(2, "A", "op5", 10, 100, "-0.02"), pos(3, "A", "op5", 350, 360, "0.03")]
    assert [b.bet_id for b, _ in cooldown_counterfactual(rows, 300)[0]] == ["b2"]
    assert [b.bet_id for b, _ in cooldown_counterfactual(rows, 300, trigger="loss")[0]] == ["b3"]


def test_concurrent_pairs_only_across_desks_and_overlapping():
    rows = [pos(1, "A", "op6", 0, 30, "0.01"), pos(2, "A", "op5", 10, 40, "-0.02"),
            pos(3, "B", "op5", 0, 10, "0.01"), pos(4, "B", "op6", 10, 20, "0.01")]  # 10 = saída: não sobrepõe
    assert [(a.bet_id, b.bet_id) for a, b in concurrent_pairs(rows)] == [("b1", "b2")]


def test_boot_diff_recovers_a_known_difference():
    rng = np.random.default_rng(0)
    a = [(f"m{i}", -0.2 + 0.01 * rng.standard_normal()) for i in range(30)]
    b = [(f"n{i}", 0.0 + 0.01 * rng.standard_normal()) for i in range(60)]
    d, lo, hi = boot_diff(a, b, n=2000, seed=1)
    assert d == pytest.approx(-0.2, abs=0.01)
    assert lo < d < hi < 0
