"""Regressão contra resultados reais e publicados: o moinho reproduz o R65 e o R67.

É esta a prova de que a ferramenta é confiável. Sintético prova que a aritmética fecha;
só os exports guardados (`.claude/state/r65/anat.csv`, `.claude/state/r67/paper.csv`,
versionados no repositório) provam que o protocolo destilado é **o mesmo** que produziu
as notas R65 e R67.

O que é exigido **exato** (não depende de gerador de números aleatórios):
n por balde, taxas de alvo, médias, D, tercis, percentis, cobertura da população e
todos os D da curva de limiares.

O que é exigido **com tolerância declarada** (erro de Monte Carlo): IC e p. A tolerância
não é arbitrária: o próprio R67 imprimiu a MESMA estatística duas vezes com estados de
RNG diferentes — `oos.txt` linha do teste primário `IC95[-0,0575, +0,1355] P=0,232` e
linha `<=25` da varredura `IC95[-0,0553, +0,1324] P=0,235`. O desacordo interno do
estudo é ≈ 0,003 no limite do IC e 0,003 em P(D≤0). Adoto **0,01** no IC (≈ 3×) e
**0,02** em P(D≤0). Para o p de permutação não afirmo o valor com tolerância apertada:
afirmo a **decisão** que ele sustentou (p ≫ 0,05) e uma folga de 0,05 em torno do
publicado — a Astra recusou, com razão, tratar ±0,05 no p como prova principal.
"""

from __future__ import annotations

import csv
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from infra.research.protocol import run_hypothesis
from infra.research.spec import (
    DecisionPolicy,
    HypothesisSpec,
    InferencePlan,
    ObservabilityWaiver,
    PreRegistration,
)
from infra.research.stats import (
    adjust_family,
    contrast,
    plateau_or_spike,
    quantile,
    quantile_buckets,
)

STATE = Path(__file__).resolve().parents[3] / ".claude" / "state"
R65 = STATE / "r65"
R67 = STATE / "r67"
BRT = timezone(timedelta(hours=-3))

CI_TOL = 0.01
P_LE0_TOL = 0.02
P_PERM_TOL = 0.05

pytestmark = pytest.mark.skipif(
    not (R65 / "anat.csv").exists() or not (R67 / "paper.csv").exists(),
    reason="exports do R65/R67 ausentes nesta árvore",
)


# ------------------------------------------------------------------------------ R65


def _r65_rows() -> list[dict[str, str]]:
    with open(R65 / "anat.csv", newline="", encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh) if r["buys_1m"].strip()]


def test_r65_tercile_table_of_buys_1m_is_reproduced() -> None:
    """`.claude/state/r65/stats.txt` linhas 22–24 e a diferença topo-base da linha 73."""
    rows = _r65_rows()
    assert len(rows) == 87
    values = [float(r["buys_1m"]) for r in rows]
    buckets = quantile_buckets(values, 3)
    assert [label for label, _ in buckets] == ["10..20", "21..37", "38..361"]

    published = [(29, 31, -0.00156), (29, 31, -0.00111), (29, 17, -0.00931)]
    for (_, idx), (n, hit, mean_pnl) in zip(buckets, published, strict=True):
        group = [rows[i] for i in idx]
        pnl = [float(g["pnl_sol"]) for g in group]
        target_rate = 100.0 * sum(1 for g in group if g["reason"] == "target") / len(group)
        assert len(group) == n
        assert round(target_rate) == hit
        assert np.mean(pnl) == pytest.approx(mean_pnl, abs=5e-6)

    top = np.array([float(rows[i]["pnl_sol"]) for i in buckets[-1][1]])
    base = np.array([float(rows[i]["pnl_sol"]) for i in buckets[0][1]])
    assert float(top.mean() - base.mean()) == pytest.approx(-0.00776, abs=5e-6)


def test_r65_money_total_is_exact_in_decimal() -> None:
    """A soma em `Decimal` do balde topo: -0,2701 SOL (`stats.txt` linha 24)."""
    rows = _r65_rows()
    values = [float(r["buys_1m"]) for r in rows]
    top = quantile_buckets(values, 3)[-1][1]
    total = sum((Decimal(rows[i]["pnl_sol"]) for i in top), Decimal(0))
    assert total.quantize(Decimal("0.0001")) == Decimal("-0.2701")


def test_r65_benjamini_hochberg_family_of_13_has_no_survivor() -> None:
    """`stats.txt` linhas 144–157: p mínimo 0,0463 contra limiar BH 0,0077."""
    published = [
        0.0463,
        0.1220,
        0.1744,
        0.2580,
        0.2680,
        0.6800,
        0.7419,
        0.8422,
        0.8469,
        0.8999,
        0.9713,
        0.9761,
        0.9993,
    ]
    family = adjust_family(published, q=0.10)
    assert family.bh_threshold[0] == pytest.approx(0.0077, abs=5e-5)
    assert family.bh_threshold[-1] == pytest.approx(0.1000, abs=5e-5)
    assert not any(family.bh_survives)
    assert not any(family.holm_survives)


# ------------------------------------------------------------------------------ R67


def _ts(value: str) -> datetime:
    text = value.strip()
    if text.endswith("+00"):
        text += ":00"
    return datetime.fromisoformat(text.replace(" ", "T"))


def _r67_population() -> tuple[list[dict[str, Any]], dict[str, int]]:
    """A fatia principal do R67, exatamente como `oos.py` a constrói."""
    excluded = set((R67 / "r65_mints.txt").read_text(encoding="utf-8").split())
    eligible: list[dict[str, Any]] = []
    with open(R67 / "paper.csv", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["status"] != "closed" or row["outcome_quality"] != "measured":
                continue
            if row["shared_live"] == "t" or not row["buys_1m"].strip():
                continue
            if not row["pnl_sol"].strip():
                continue
            entry = _ts(row["entry_at"])
            size = Decimal(row["size_sol"].strip() or "0.05")
            pnl = Decimal(row["pnl_sol"])
            eligible.append(
                {
                    "mint": row["mint"],
                    "arm": row["arm"],
                    "entry_at": entry,
                    "day": entry.astimezone(BRT).date().isoformat(),
                    "ret": float(pnl / size),
                    "pnl_sol": pnl,
                    "buys_1m": float(row["buys_1m"]),
                }
            )
    flow = [r for r in eligible if str(r["arm"]).startswith("flow_v2")]
    without_r65 = [r for r in flow if r["mint"] not in excluded]
    oldest: dict[str, dict[str, Any]] = {}
    for row in sorted(without_r65, key=lambda r: r["entry_at"]):
        oldest.setdefault(row["mint"], row)
    main = list(oldest.values())
    coverage = {
        "eligible": len(eligible),
        "flow_v2": len(flow),
        "without_r65": len(without_r65),
        "dedup": len(main),
    }
    return main, coverage


def _r67_spec(rows: list[dict[str, Any]], reps: int) -> HypothesisSpec:
    return HypothesisSpec(
        name="R67 — buys_1m <= 25 fora de amostra",
        origin="R65 (achado in-sample nas 87 operações reais)",
        loader=lambda: rows,
        decision_instant="entry_at",
        outcome="ret",
        variable="buys_1m",
        direction="low",
        observability=ObservabilityWaiver(
            "`buys_1m` vem de `meme_proposals.reasons`, gravado NO INSTANTE DA DECISÃO; "
            "o export de 2026-09-23 não traz as colunas de relógio da linha de feature"
        ),
        inference=InferencePlan(
            cluster="mint",
            stratum="day",
            thresholds=(10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 60.0, 80.0),
            reps=reps,
            seed=67,
        ),
        policy=DecisionPolicy(frozen_threshold=25.0, minimum_effect=0.01),
        pre_registration=PreRegistration(
            prediction="Δ = média(ret | buys_1m ≤ 25) − média(ret | > 25) é positivo",
            refutation="IC 95 % por bootstrap de mint cobrindo zero, ou p ≥ 0,05",
            decision_rule=(
                "confirmado só com Δ>0 E IC 95 % inteiramente positivo E p de permutação "
                "< 0,05; caso contrário não confirmado, e não procuro outro corte"
            ),
            registered_on="2026-09-23",
            threshold_policy="fixo 25, congelado antes de ver a fatia de papel",
        ),
        money_column="pnl_sol",
        assumptions=(
            "apostas de papel flow_v2 correm 0,05 SOL / alvo 3× / 1800 s / trailing 35 %; "
            "a mesa real corre 0,07 / 1,15× / 300 s / trailing 10 %",
            "tamanho ausente assumido 0,05 SOL",
        ),
    )


def test_r67_population_coverage_is_reproduced() -> None:
    """`oos.txt`: papel elegível 1143 | flow_v2 1069 | sem mints do R65 971 | dedup 473."""
    _, coverage = _r67_population()
    assert coverage == {"eligible": 1143, "flow_v2": 1069, "without_r65": 971, "dedup": 473}


def test_r67_distribution_of_buys_1m_is_reproduced() -> None:
    """`oos.txt`: p10=13 p25=20 mediana=31 p75=57 p90=97; ≤ 25 em 37,2 % da fatia."""
    rows, _ = _r67_population()
    values = [float(r["buys_1m"]) for r in rows]
    assert [quantile(values, q) for q in (0.10, 0.25, 0.50, 0.75, 0.90)] == [13, 20, 31, 57, 97]
    share = 100.0 * sum(1 for v in values if v <= 25) / len(values)
    assert share == pytest.approx(37.2, abs=0.05)


def test_r67_frozen_primary_test_is_reproduced_end_to_end() -> None:
    """O teste primário congelado do R67, corrido pelo moinho em vez do script do estudo."""
    rows, _ = _r67_population()
    report = run_hypothesis(_r67_spec(rows, reps=10_000))

    # exatos
    assert report.n_used == 473
    assert (report.contrast.n_selected, report.contrast.n_rest) == (176, 297)
    assert report.contrast.mean_selected == pytest.approx(-0.0000, abs=5e-5)
    assert report.contrast.mean_rest == pytest.approx(-0.0358, abs=5e-5)
    assert report.contrast.d == pytest.approx(+0.0358, abs=5e-5)

    # com tolerância de Monte Carlo declarada no docstring do módulo
    assert report.contrast.ci.lo == pytest.approx(-0.0575, abs=CI_TOL)
    assert report.contrast.ci.hi == pytest.approx(+0.1355, abs=CI_TOL)
    assert report.contrast.ci.p_le0 == pytest.approx(0.232, abs=P_LE0_TOL)
    assert report.contrast.p_perm > 0.05
    assert report.contrast.p_perm == pytest.approx(0.4273, abs=P_PERM_TOL)

    # o veredito publicado: não confirmado (e não é refutação)
    assert report.verdict == "NÃO CONFIRMA"


def test_r67_threshold_curve_is_reproduced_and_is_a_spike() -> None:
    """`oos.txt` secção 3 — e a leitura da KB-0149 §3 item 12: pico, não patamar."""
    rows, _ = _r67_population()
    report = run_hypothesis(_r67_spec(rows, reps=10_000))
    published = {
        15: +0.1550,
        20: +0.0779,
        25: +0.0358,
        30: +0.0390,
        40: +0.0331,
        60: -0.0037,
        80: +0.0843,
    }
    by_threshold = {int(p.threshold): p for p in report.curve}
    assert by_threshold[10].evaluable is False  # n = 10/463, amostra insuficiente
    for threshold, d in published.items():
        assert by_threshold[threshold].d == pytest.approx(d, abs=5e-5)
    assert by_threshold[15].ci.lo > 0  # o único limiar com IC acima de zero
    assert report.shape.form == "pico"
    assert (report.shape.longest_run, report.shape.ci_clear) == (5, 1)


def test_r67_tercile_buckets_are_reproduced() -> None:
    """`oos.txt` secção 2: tercis 23/43, n 159/157/157, ret médio +0,0068/−0,0217/−0,0530."""
    rows, _ = _r67_population()
    report = run_hypothesis(_r67_spec(rows, reps=1000))
    assert [b.n for b in report.buckets] == [159, 157, 157]
    assert [round(b.mean, 4) for b in report.buckets] == [0.0068, -0.0217, -0.0530]


def test_r67_leave_one_day_out_is_reproduced() -> None:
    """`oos.txt` secção 5(c): o sinal de D por dia removido, sem nenhum RNG envolvido."""
    rows, _ = _r67_population()
    published = {
        "2026-09-12": +0.0289,
        "2026-09-13": +0.0079,
        "2026-09-14": +0.0419,
        "2026-09-15": +0.0430,
        "2026-09-16": +0.0407,
        "2026-09-17": +0.0520,
        "2026-09-18": +0.0226,
        "2026-09-19": +0.0361,
        "2026-09-20": +0.0560,
        "2026-09-21": +0.0326,
    }
    for day, expected in published.items():
        rest = [r for r in rows if r["day"] != day]
        y = np.array([float(r["ret"]) for r in rest])
        sel = np.array([float(r["buys_1m"]) <= 25.0 for r in rest])
        assert contrast(y, sel) == pytest.approx(expected, abs=5e-5)


def test_r67_money_total_of_the_main_slice_is_decimal() -> None:
    rows, _ = _r67_population()
    report = run_hypothesis(_r67_spec(rows, reps=500))
    assert isinstance(report.money_total, Decimal)
    assert report.money_total == sum((Decimal(str(r["pnl_sol"])) for r in rows), Decimal(0))


def test_r67_verdict_holds_under_r67s_own_frozen_rule_too() -> None:
    """Separa "reproduz o R67" de "aplica a política nova aos dados do R67" (Astra).

    A regra congelada do R67 (emenda 1, item 5) era só: Δ>0 **e** IC 95 % inteiramente
    positivo **e** p de permutação < 0,05. Sem os portões que o moinho acrescentou
    (planalto, nível positivo), o veredito continua o mesmo — a coincidência não vem dos
    portões extra.
    """
    rows, _ = _r67_population()
    spec = _r67_spec(rows, reps=4000)
    own_rule = replace(
        spec,
        policy=DecisionPolicy(
            frozen_threshold=25.0,
            minimum_effect=0.01,
            require_plateau=False,
            require_positive_level=False,
        ),
    )
    report = run_hypothesis(own_rule)
    assert report.verdict == "NÃO CONFIRMA"
    assert "IC 95 % inferior" in " ".join(report.reasons)


def test_the_mill_would_not_have_confirmed_the_r67_hypothesis() -> None:
    """A regra congelada do moinho chega ao mesmo veredito que o estudo, pelos mesmos motivos."""
    rows, _ = _r67_population()
    report = run_hypothesis(_r67_spec(rows, reps=4000))
    assert report.verdict == "NÃO CONFIRMA"
    joined = " ".join(report.reasons)
    assert "IC 95 % inferior" in joined
    assert "pico" in joined
    assert plateau_or_spike(report.curve).form == "pico"
