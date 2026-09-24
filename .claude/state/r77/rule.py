"""R77 / H-016 — contraste emparelhado pelo moinho e a regra de decisão congelada (notes-R77 §1.8 + §9).

`mill_paired` empilha 2 linhas por decisão (braço 1 = política, 0 = controlo) e corre `run_hypothesis`
com `cluster = stratum = mint`: o bootstrap sorteia mints inteiros (par inteiro) e a permutação dentro do
mint é a troca de sinal do par. O D do moinho é a média por decisão de `r_política − r_controlo`.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infra.research.protocol import run_hypothesis  # noqa: E402
from infra.research.spec import (  # noqa: E402
    DecisionPolicy,
    HypothesisSpec,
    InferencePlan,
    ObservabilityWaiver,
    PreRegistration,
)

MRE = 0.05
REFUT = 0.01
EDGE_X = (3, 12)
XS = (3, 5, 8, 12)
WS = (20, 60)
_T = datetime(2026, 9, 23, tzinfo=UTC)

PRE = PreRegistration(
    prediction=("existe uma célula (X, W) que rende mais +0,05 por SOL decidido que o controlo (diferença "
                "emparelhada por decisão, 0 para quem não entrou), com IC 95 % (bootstrap por mint, 10 000) "
                "inteiramente acima de zero, e patamar (um vizinho em X no mesmo sentido); nas reais, a fração "
                "de perdas que nunca passaram do custo cai"),
    refutation=("nenhuma célula com limite inferior do IC acima de +0,01 por SOL; ou a melhor célula na borda "
                "da grade; ou o ganho some com 5 s de atraso no pouso; ou o ganho vem só de 'não entrar' (a "
                "célula não bate a política 'não comprar nada', retorno 0)"),
    decision_rule="notes-R77 §1.8 com as emendas §9 (regra própria; o veredito do moinho não decide)",
    registered_on="2026-09-23",
    threshold_policy="grade X ∈ {3,5,8,12} %, W ∈ {20,60} s congelada na fila; limiar do braço 0,5 (0/1)",
)


def mill_paired(pol, ctrl, mints, name: str, reps: int = 10_000, seed: int = 77) -> dict:
    if not (len(pol) == len(ctrl) == len(mints)) or len(set(mints)) != len(mints):
        raise ValueError("um par por mint, listas do mesmo tamanho")
    rows = []
    for a, b, m in zip(pol, ctrl, mints, strict=True):
        rows.append(dict(t=_T, mint=m, arm=1, ret=float(a)))
        rows.append(dict(t=_T, mint=m, arm=0, ret=float(b)))
    spec = HypothesisSpec(
        name=name, origin="H-016 / R77", loader=lambda: rows, decision_instant="t", outcome="ret",
        variable="arm", direction="high",
        observability=ObservabilityWaiver(
            "a anti-antecipação daqui é a View do motor de entrada (entry.py, test_r77.py); "
            "as linhas são braços simulados, não features com instante"),
        inference=InferencePlan(cluster="mint", stratum="mint", thresholds=(0.5,), reps=reps, seed=seed),
        policy=DecisionPolicy(frozen_threshold=0.5, minimum_effect=MRE, min_per_side=20),
        pre_registration=PRE,
        assumptions=("custo 2,23 % ida e volta", "pouso = gatilho + L", "saída 1,15x / 10 % / 300 s"),
    )
    rep = run_hypothesis(spec)
    c = rep.contrast
    return dict(D=c.d, lo=c.ci.lo, hi=c.ci.hi, p=c.p_perm, n=len(pol), mill=rep.verdict,
                fingerprint=rep.fingerprint, level=c.mean_selected)


def holm(pvals: dict) -> dict:
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m, out, run = len(items), {}, 0.0
    for k, (name, p) in enumerate(items):
        run = max(run, min(1.0, (m - k) * p))
        out[name] = run
    return out


def _neighbours(x: int) -> list[int]:
    k = XS.index(x)
    return [XS[j] for j in (k - 1, k + 1) if 0 <= j < len(XS)]


def best_cell(cells: dict):
    return max(cells, key=lambda n: (cells[n]["D"], n[0] not in EDGE_X))


def decide(cells: dict, frac_falls) -> tuple[str, list[str]]:
    """`cells[(x, w)] = {D, lo, level, D5}`; `frac_falls` bool ou {célula: bool}. Refutação tem precedência."""
    ff = (lambda n: frac_falls) if isinstance(frac_falls, bool) else (lambda n: frac_falls[n])
    why: list[str] = []
    best = best_cell(cells)
    b = cells[best]
    ref_a = all(c["lo"] <= REFUT for c in cells.values())
    if ref_a:
        why.append("(a) nenhuma célula com IC inferior > +0,01 (maior = %+.4f)"
                   % max(c["lo"] for c in cells.values()))
    ref_b = best[0] in EDGE_X
    if ref_b:
        why.append("(b) melhor célula X=%d%% W=%ds (D %+.4f) na borda em X" % (best[0], best[1], b["D"]))
    ref_c = b["D"] > 0 and b["D5"] <= 0
    if ref_c:
        why.append("(c) X=%d%% W=%ds: D %+.4f a 1,6 s vira %+.4f a 5 s" % (best[0], best[1], b["D"], b["D5"]))
    ref_d = b["level"] <= 0
    if ref_d:
        why.append("(d) X=%d%% W=%ds não bate 'não comprar nada': retorno médio por SOL decidido %+.4f"
                   % (best[0], best[1], b["level"]))
    why.append("melhor célula X=%d%% W=%ds: D %+.4f (IC inf %+.4f), 5 s %+.4f, nível %+.4f"
               % (best[0], best[1], b["D"], b["lo"], b["D5"], b["level"]))
    conf = [n for n, c in cells.items()
            if c["D"] >= MRE and c["lo"] > 0 and ff(n)
            and any(cells[(x, n[1])]["D"] > 0 for x in _neighbours(n[0]))]
    if conf:
        why.append("cumprem a previsão: " + ", ".join("X=%d%% W=%ds" % n for n in conf))
    if ref_a or ref_b or ref_c or ref_d:
        return "REFUTA", why
    if conf:
        return "CONFIRMA", why
    why.append("nenhuma célula cumpre D >= +0,05, IC inferior > 0, patamar em X (e a fração, nas reais)")
    return "NÃO CONFIRMA", why


def combine(real: str, paper: str) -> str:
    if real == paper and real in ("CONFIRMA", "REFUTA"):
        return real
    return "NÃO CONFIRMA"
