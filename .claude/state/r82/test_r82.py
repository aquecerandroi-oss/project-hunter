# R82 — testes sintéticos com valores conhecidos (classificação, população, par, mesma foto, estatística, rótulo).
# cd .claude/state/r82 && uv run --project C:/dev/project-hunter pytest -q test_r82.py
import numpy as np
import pytest

from h017 import classify_arm, classify_ctl, pair_rows, part, population, same_snapshot
from h017_stats import (
    boot_paired, decompose, fixed_exit_counterfactual, label, price_gap, sign_flip_p, vs_nothing,
)

BASE = {
    "extracted_at": "2026-09-27 20:00:00+00", "mint": "M1", "symbol": "S", "t0": "2026-09-27 12:00:00+00",
    "outcomes": "", "arm_prop": "", "arm_bet": "", "arm_status": "", "arm_pnl": "", "arm_size": "0.07", "arm_oq": "",
    "arm_snap_at": "", "arm_vsol": "", "arm_vtok": "", "ctl_prop": "p", "ctl_bet": "b", "ctl_status": "closed",
    "ctl_pnl": "-0.007", "ctl_size": "0.07", "ctl_oq": "ok", "ctl_first_fet": "2026-09-27 12:00:00+00",
    "ctl_snap_at": "2026-09-27 12:00:09+00", "ctl_vsol": "30", "ctl_vtok": "1000",
}


def row(**kw):
    return dict(BASE, **kw)


def entered(pnl="0.0035", snap="2026-09-27 12:00:09+00", vsol="30", vtok="1000", **kw):
    base = dict(arm_prop="a", arm_bet="ab", arm_status="closed", arm_pnl=pnl, arm_oq="ok", arm_snap_at=snap,
                arm_vsol=vsol, arm_vtok=vtok)
    return row(**{**base, **kw})


def test_arm_entered_return_is_pnl_over_sol_spent():
    assert classify_arm(entered()) == ("entered", pytest.approx(0.05))


def test_arm_non_entries_are_zero_and_censored_out():
    assert classify_arm(row(outcomes="no_pullback@2026-09-27 12:01:00+00#1.2")) == ("no_pullback", 0.0)
    assert classify_arm(row(outcomes="pullback_killed:creator_sold_during_wait@x#")) == ("killed", 0.0)
    assert classify_arm(row(outcomes="pullback_censored:feed_lost@x#")) == ("censored", None)
    assert classify_arm(row(outcomes="pullback_dropped_cap@x#")) == ("censored", None)
    assert classify_arm(row()) == ("no_outcome", None)
    # a 1.ª linha de desfecho manda
    assert classify_arm(row(outcomes="pullback_censored:x@a# | no_pullback@b#"))[0] == "censored"


def test_arm_indeterminate_open_and_unfilled_are_out():
    assert classify_arm(entered(arm_oq="indeterminate")) == ("indeterminate", None)
    assert classify_arm(entered(arm_status="open", pnl="")) == ("open", None)
    assert classify_arm(row(arm_prop="a")) == ("prop_no_bet", None)


def test_control_classes():
    assert classify_ctl(row()) == ("resolved", pytest.approx(-0.1))
    assert classify_ctl(row(ctl_prop="", ctl_first_fet="2026-09-27 11:58:00+00")) == ("absent_already_open", None)
    assert classify_ctl(row(ctl_prop="", ctl_first_fet="")) == ("absent", None)
    assert classify_ctl(row(ctl_bet="")) == ("unfilled", None)
    assert classify_ctl(row(ctl_oq="indeterminate")) == ("indeterminate", None)


def test_population_cutoff_is_blind_to_outcome():
    rows = [entered(t0="2026-09-27 19:44:00+00"), entered(t0="2026-09-27 19:46:00+00"),
            entered(t0="2026-09-26 15:05:00+00")]
    pop, cnt = population(rows)
    assert [r["t0"] for r in pop] == ["2026-09-27 19:44:00+00"]
    assert cnt == {"in": 1, "in_flight": 1, "before_cohort": 1}
    changed = [dict(r, arm_pnl="-0.07", ctl_pnl="0.5") for r in rows]
    assert [r["t0"] for r in population(changed)[0]] == ["2026-09-27 19:44:00+00"]


def test_pairs_drop_missing_control_and_count_it():
    rows = [entered(mint="A"), row(mint="B", outcomes="no_pullback@x#"), entered(mint="C", ctl_bet="")]
    pairs, why = pair_rows(rows)
    assert [p["mint"] for p in pairs] == ["A", "B"]
    assert why["ctl:unfilled"] == 1 and why["arm:entered"] == 2
    assert pairs[1]["ra"] == 0.0 and pairs[1]["rc"] == pytest.approx(-0.1)


def test_same_snapshot_needs_time_and_reserves():
    p = dict(entered(), cls="entered")
    assert same_snapshot(p) and part(p) == "mesma_foto"
    assert not same_snapshot(dict(p, arm_vsol="31")) and part(dict(p, arm_vsol="31")) == "foto_posterior"
    assert not same_snapshot(dict(p, arm_snap_at="2026-09-27 12:00:12+00"))
    assert part(dict(p, cls="killed")) == "nao_entrou"
    # sem metadados da foto em algum lado: desconhecida, nunca 'posterior'
    assert part(dict(p, ctl_snap_at="")) == "foto_desconhecida"
    assert part(dict(p, arm_vsol="")) == "foto_desconhecida"


def test_paired_bootstrap_matches_direct_and_known_mean():
    rng = np.random.default_rng(0)
    ra, rc = rng.normal(0.02, 0.1, 200), rng.normal(0.0, 0.1, 200)
    mints = [f"m{i}" for i in range(200)]
    d, lo, hi = boot_paired(ra, rc, mints, reps=4000, seed=1)
    assert d == pytest.approx(float((ra - rc).mean()))
    direct = (ra - rc)[np.random.default_rng(2).integers(0, 200, (4000, 200))].mean(1)
    dlo, dhi = np.percentile(direct, [2.5, 97.5])
    assert lo == pytest.approx(dlo, abs=0.004) and hi == pytest.approx(dhi, abs=0.004)


def test_vs_nothing_is_mean_of_arm_with_bootstrap():
    ra = np.array([0.1, -0.05, 0.0, 0.2])
    m, lo, hi = vs_nothing(ra, ["a", "b", "c", "d"], reps=2000, seed=3)
    assert m == pytest.approx(0.0625) and lo <= m <= hi


def test_sign_flip_p_detects_constant_shift_and_not_symmetric_noise():
    ra = np.full(40, 0.05) + np.linspace(-0.001, 0.001, 40)
    assert sign_flip_p(ra, np.zeros(40), [str(i) for i in range(40)], reps=2000, seed=4) < 0.01
    x = np.array([0.1, -0.1] * 20)
    assert sign_flip_p(x, np.zeros(40), [str(i) for i in range(40)], reps=2000, seed=4) > 0.5


@pytest.mark.parametrize("n,d,ra,expected", [
    (149, (0.05, 0.03, 0.08), (0.02, 0.01, 0.03), "LIMITE DE DADO"),
    (150, (0.0, -0.02, 0.009), (0.02, 0.01, 0.03), "REFUTA (a)"),
    (150, (0.03, 0.005, 0.06), (-0.04, -0.07, -0.01), "REFUTA (b)"),
    (150, (0.03, 0.005, 0.06), (0.02, 0.001, 0.04), "CONFIRMA"),
    (150, (0.03, 0.005, 0.06), (0.01, -0.02, 0.04), "NÃO CONFIRMA"),   # (b) literal só
    (150, (0.015, 0.001, 0.03), (0.02, 0.01, 0.03), "NÃO CONFIRMA"),   # D < MRE
    (150, (0.03, -0.001, 0.06), (0.02, 0.01, 0.03), "NÃO CONFIRMA"),   # IC de D contém zero
])
def test_label_rule_order(n, d, ra, expected):
    assert label(n, d, ra).startswith(expected)


def test_decomposition_sums_to_D():
    pairs = [dict(cls="entered", ra=0.1, rc=0.1, **{"_p": "mesma_foto"}),
             dict(cls="entered", ra=0.05, rc=-0.05, **{"_p": "foto_posterior"}),
             dict(cls="killed", ra=0.0, rc=-0.3, **{"_p": "nao_entrou"}),
             dict(cls="no_pullback", ra=0.0, rc=0.15, **{"_p": "nao_entrou"})]
    parts = decompose(pairs, key=lambda p: p["_p"] if p["cls"] == "entered" else p["cls"])
    assert sum(c for _, c, _ in parts.values()) == pytest.approx(np.mean([p["ra"] - p["rc"] for p in pairs]))
    assert parts["killed"][1] == pytest.approx(0.3 / 4)


def test_price_gap_and_fixed_exit_counterfactual():
    # controle comprou a 1,00; gatilho a 0,97 → o papel apagou 1/0,97 − 1 = +3,09 % de preço
    assert price_gap(1.0, 0.97) == pytest.approx(1 / 0.97 - 1)
    # r_c = +10 % → r_a' = 1,10 × 1/0,97 − 1
    assert fixed_exit_counterfactual(0.10, 1.0, 0.97) == pytest.approx(1.10 / 0.97 - 1)
    assert fixed_exit_counterfactual(-1.0, 1.0, 0.97) == pytest.approx(-1.0)  # perda total não melhora


def test_decision_price_sensitivity_reprices_entries_only():
    from h017_stats import decision_price_sensitivity
    ent = {"cls": "entered", "ra": 0.10, "rc": 0.20, "arm_mpx_before": "1.0", "ctl_mpx_before": "1.1",
           "pb": '{"trigger_price": "0.97", "t0_price": "1.0"}'}
    non = {"cls": "killed", "ra": 0.0, "rc": -0.30, "arm_mpx_before": "", "ctl_mpx_before": "1.0", "pb": ""}
    ra2, rc2, n_rep = decision_price_sensitivity([ent, non])
    assert ra2[0] == pytest.approx(1.10 * 1.0 / 0.97 - 1)
    assert rc2[0] == pytest.approx(1.20 * 1.1 / 1.0 - 1)
    assert (ra2[1], rc2[1]) == (0.0, -0.30)  # não-entrada mantida como observada (sem t0_price no bloco)
    assert n_rep == 1
