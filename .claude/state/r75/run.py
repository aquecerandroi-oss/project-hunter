"""R75 — H-013: `equilibrio` (vendas÷compras ≥ 0,6 E fluxo < 2 SOL/min E progresso < 25 %).

Cobertura, moinho (`run_hypothesis`), patamar ±1 degrau por limiar, previsão secundária
(perdas ≥ 15 % em ≤ 3 s), exploratório (condições sozinhas e aos pares — FORA do
veredito) e o contrafactual sobre as posições reais. Sinal dos quadros: D_bloco =
média(equilíbrio) − média(resto), o sinal do pré-registo; o moinho corre o espelho.
"""

from __future__ import annotations

import itertools
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from load import (
    FROZEN,
    Row,
    Thresholds,
    features,
    in_population,
    load,
    population,
)

from infra.research.protocol import run_hypothesis
from infra.research.report import render
from infra.research.resampling import cluster_bootstrap
from infra.research.spec import (
    DecisionPolicy,
    HypothesisSpec,
    InferencePlan,
    ObservabilityWaiver,
    PreRegistration,
)

HERE = Path(__file__).resolve().parent
REPS, SEED, MIN_SIDE = 10_000, 75, 20
# degraus congelados ANTES de olhar desfechos (suposição declarada nas notas)
STEPS = {"ratio": 0.1, "flow": Decimal("1"), "progress": Decimal("5")}
PRE = PreRegistration(
    prediction=(
        "decisões com `equilibrio = verdadeiro` rendem menos −0,05 por SOL que as demais, e "
        "concentram a fração de perdas ≥ 15 % em até 3 s de posição (saída imediata pelo recuo)"
    ),
    refutation=(
        "limite inferior do IC 95 % (bootstrap por mint) acima de −0,01 por SOL; ou menos de 20 "
        "decisões com `equilibrio = verdadeiro` (poucas demais para julgar — registrar como "
        "limite de dado); ou os três limiares escolhidos não formam patamar quando cada um é "
        "deslocado ±1 degrau"
    ),
    decision_rule=(
        "CONFIRMA com D>0 (resto−equilíbrio, espelho do bloco), IC inferior>0, p<0,05, D≥MRE "
        "0,05, braço selecionado lucrativo em nível. Planalto do moinho DESLIGADO porque a "
        "variável é booleana (degrau real); o patamar pré-registado é verificado fora do "
        "moinho, deslocando cada limiar ±1 degrau (0,1 / 1 SOL / 5 pp)."
    ),
    registered_on="2026-09-23",
    threshold_policy="fixos, congelados no pré-registo: 0,6 / 2 SOL por min / 25 %",
)


def eq(r: Row, t: Thresholds = FROZEN) -> bool | None:
    return features(r, t)["equilibrio"]


def pnl(rows: list[Row]) -> Decimal:
    return sum((r["pnl_sol"] for r in rows), Decimal(0))  # type: ignore[misc]


def contrast(rows: list[Row], mask: list[bool], seed: int) -> str:
    """n, médias, D_bloco = média(marcadas) − média(resto) e IC de cluster por mint."""
    y = np.array([float(r["ret"]) for r in rows])  # type: ignore[arg-type]
    m = np.array(mask, dtype=bool)
    ns, nr = int(m.sum()), int((~m).sum())
    if ns == 0 or nr == 0:
        return f"{ns} | {nr} | — | — | — | —"
    d = float(y[m].mean() - y[~m].mean())
    if ns < MIN_SIDE or nr < MIN_SIDE:
        ci = "sem potência (< 20 por lado)"
    else:
        iv = cluster_bootstrap(y, m, [r["mint"] for r in rows], reps=REPS, seed=seed)
        ci = f"[{iv.lo:+.4f}, {iv.hi:+.4f}]"
    return f"{ns} | {nr} | {y[m].mean():+.4f} | {y[~m].mean():+.4f} | {d:+.4f} | {ci}"


def cobertura(rows: list[Row]) -> list[str]:
    live = [r for r in rows if r["lane"] == "live"]
    opm, _ = population(rows)
    out = [
        "## 1. Cobertura", "",
        "| recorte | linhas | porta fluxo_e_holders | bloco `flow` | progresso | as três lidas |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label, sub in (("posições reais", live), ("papel", [r for r in rows if r["lane"] == "paper"]),
                       ("uma por mint (população)", opm)):
        g = [r for r in sub if str(r["gate"]).startswith("fluxo_e_holders/")]
        three = sum(1 for r in g if eq(r) is not None)
        out.append(f"| {label} | {len(sub)} | {len(g)} | {sum(bool(r['has_flow']) for r in g)} | "
                   f"{sum(r['progress'] is not None for r in g)} | {three} ({three / len(sub):.1%}) |")
    out += ["", f"Séries: {dict(Counter(str(r['series']) for r in opm))}",
            f"Teto `max_sells_to_buys` da porta (uma por mint): "
            f"{dict(Counter(str(r['cap_ratio']) for r in opm))}", ""]
    out += ["| braço | teto razão | n | razão ≥ 0,6 | fluxo < 2 | progresso < 25 | **equilíbrio** |",
            "|---|---:|---:|---:|---:|---:|---:|"]
    for (rs, cap), g in sorted(_group(opm, lambda r: (r["rule_set"], str(r["cap_ratio"]))).items()):
        f = [features(r, FROZEN) for r in g]
        out.append(f"| {rs} | {cap} | {len(g)} | {sum(bool(x['c_ratio']) for x in f)} | "
                   f"{sum(bool(x['c_flow']) for x in f)} | {sum(bool(x['c_prog']) for x in f)} | "
                   f"**{sum(bool(x['equilibrio']) for x in f)}** |")
    return out


def _group(rows: list[Row], key) -> dict[object, list[Row]]:  # type: ignore[no-untyped-def]
    out: dict[object, list[Row]] = {}
    for r in rows:
        out.setdefault(key(r), []).append(r)
    return out


def moinho(opm: list[Row]) -> str:
    data = [dict(r, eq_i=1.0 if eq(r) else 0.0) for r in opm]
    spec = HypothesisSpec(
        name="H-013 — moeda em equilíbrio (resto × equilíbrio)",
        origin="perda real SHORT 23/09/2026 17:39 BRT (−18,7 %)",
        loader=lambda: data, decision_instant="decided_at", outcome="ret", variable="eq_i",
        direction="low",
        observability=ObservabilityWaiver(reason=(
            "as três grandezas são lidas de meme_proposals.reasons, gravadas pela porta no "
            "instante da decisão; não há fita reconstruída nem coluna de instante a guardar")),
        inference=InferencePlan(cluster="mint", stratum="dia", block="hora", thresholds=(0.5,),
                                reps=REPS, seed=SEED),
        policy=DecisionPolicy(frozen_threshold=0.5, minimum_effect=0.05, require_plateau=False),
        pre_registration=PRE, money_column="pnl_sol",
        assumptions=("desfecho = pnl_sol / tamanho sob a saída de cada braço; custo já no pnl",
                     "uma decisão por mint: real > papel, depois a mais antiga (regra do R73)"),
    )
    return render(run_hypothesis(spec))


def patamar(opm: list[Row]) -> list[str]:
    out = ["## 3. Patamar — cada limiar deslocado ±1 degrau (grelha 3×3×3)", "",
           "D_bloco = média(equilíbrio) − média(resto). Os 7 pontos da regra (centro + 6 "
           "vizinhos de um eixo só) marcados com ●.", "",
           "| razão ≥ | fluxo < | progresso < | ● | n equilíbrio | n resto | média eq | média resto "
           "| D_bloco | IC 95 % (mint) |", "|---:|---:|---:|:-:|---:|---:|---:|---:|---:|---|"]
    base = (FROZEN.ratio, FROZEN.flow, FROZEN.progress)
    for j, k in enumerate(itertools.product((-1, 0, 1), repeat=3)):
        t = Thresholds(round(base[0] + k[0] * STEPS["ratio"], 2),
                       base[1] + k[1] * STEPS["flow"], base[2] + k[2] * STEPS["progress"])
        dot = "●" if sum(abs(x) for x in k) <= 1 else ""
        mask = [bool(eq(r, t)) for r in opm]
        out.append(f"| {t.ratio} | {t.flow} | {t.progress} | {dot} | "
                   f"{contrast(opm, mask, SEED + 100 + j)} |")
    return out


def secundaria(opm: list[Row]) -> list[str]:
    out = ["## 4. Previsão secundária — perdas ≥ 15 % que saem em ≤ 3 s", "",
           "| grupo | n | perdas ≥ 15 % | das quais em ≤ 3 s | fração | perda rápida / n |",
           "|---|---:|---:|---:|---:|---:|"]
    for label, g in (("equilíbrio", [r for r in opm if eq(r)]),
                     ("resto", [r for r in opm if eq(r) is False])):
        big = [r for r in g if float(r["ret"]) <= -0.15]  # type: ignore[arg-type]
        fast = [r for r in big if r["hold_s"] is not None and float(r["hold_s"]) <= 3]  # type: ignore[arg-type]
        frac = f"{len(fast) / len(big):.1%}" if big else "—"
        out.append(f"| {label} | {len(g)} | {len(big)} | {len(fast)} | {frac} | "
                   f"{len(fast) / len(g):.1%} |" if g else f"| {label} | 0 | — | — | — | — |")
    return out


def exploratorio(opm: list[Row]) -> list[str]:
    out = ["## 5. EXPLORATÓRIO — condições sozinhas e aos pares (fora do veredito)", "",
           "| condição | n verdadeiro | n falso | média verd. | média falso | D (verd − falso) "
           "| IC 95 % (mint) |", "|---|---:|---:|---:|---:|---:|---|"]
    names = {"c_ratio": "vendas÷compras ≥ 0,6", "c_flow": "fluxo < 2 SOL/min",
             "c_prog": "progresso < 25 %"}
    combos = [(k,) for k in names] + list(itertools.combinations(names, 2))
    for j, combo in enumerate(combos):
        mask = [all(bool(features(r, FROZEN)[c]) for c in combo) for r in opm]
        label = " E ".join(names[c] for c in combo)
        out.append(f"| {label} | {contrast(opm, mask, SEED + 300 + j)} |")
    return out


def contrafactual(rows: list[Row]) -> list[str]:
    live = [r for r in rows if r["lane"] == "live"]
    total, wins = pnl(live), sum(1 for r in live if r["pnl_sol"] > 0)  # type: ignore[operator]
    out = ["## 6. Contrafactual — a porta recusando `equilibrio = verdadeiro`", "",
           f"Base: {len(live)} posições reais (todas, não uma por mint), {wins} vencedoras, "
           f"PnL **{total:+.4f} SOL**.", "",
           "| limiares | bloqueadas | vencedoras mortas | PnL removido | PnL com a regra | Δ |",
           "|---|---:|---:|---:|---:|---:|"]
    base = (FROZEN.ratio, FROZEN.flow, FROZEN.progress)
    for k in [(0, 0, 0), (-1, 0, 0), (1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1),
              (-1, 1, 1)]:
        t = Thresholds(round(base[0] + k[0] * STEPS["ratio"], 2),
                       base[1] + k[1] * STEPS["flow"], base[2] + k[2] * STEPS["progress"])
        blk = [r for r in live if eq(r, t)]
        dead = [r for r in blk if r["pnl_sol"] > 0]  # type: ignore[operator]
        tag = "**congelado**" if k == (0, 0, 0) else ("mais largo (todos +1)" if k == (-1, 1, 1)
                                                        else "vizinho")
        out.append(f"| {t.ratio} / {t.flow} / {t.progress} ({tag}) | {len(blk)} | "
                   f"{len(dead)} {[str(r['symbol']) for r in dead]} | {pnl(blk):+.4f} | "
                   f"{total - pnl(blk):+.4f} | {-pnl(blk):+.4f} |")
    out += ["", "Bloqueadas no limiar congelado:"]
    for r in [r for r in live if eq(r)]:
        out.append(f"- `{r['symbol']}` {r['decided_at']:%Y-%m-%d %H:%M:%S} UTC — compras "
                   f"{r['buys']} × vendas {r['sells']} (razão {float(r['ratio']):.2f}), fluxo "  # type: ignore[arg-type]
                   f"{r['net_flow']} SOL/min, progresso {r['progress']} %, PnL {r['pnl_sol']:+} "
                   f"SOL ({float(r['ret']):+.1%}), posição {r['hold_s']} s, saída {r['exit_reason']}")  # type: ignore[arg-type]
    return out


if __name__ == "__main__":
    rows = load()
    opm, censored = population(rows)
    n_eq = sum(bool(eq(r)) for r in opm)
    parts = cobertura(rows)
    parts += ["", f"**Decisões com `equilibrio = verdadeiro` (uma por mint): {n_eq} de {len(opm)}** "
              f"(todas as linhas: {sum(bool(eq(r)) for r in rows if in_population(r))} de "
              f"{sum(1 for r in rows if in_population(r))}). Censuradas depois de escolher uma por "
              f"mint: {len(censored)}.", "", "## 2. Moinho", ""]
    parts += [moinho(opm), ""]
    parts += ["> **Leitura obrigatória (achado da Astra):** com 1 caso de um lado, o IC e o "
              "`P(D≤0)` acima NÃO são interpretáveis — nas réplicas que sobrevivem o SHORT "
              "está sempre lá com o mesmo retorno e as outras são descartadas. Não citar como "
              "evidência. O veredito do moinho (amostra insuficiente) é o que vale.", ""]
    parts += patamar(opm) + [""] + secundaria(opm) + [""] + exploratorio(opm) + [""]
    parts += contrafactual(rows)
    txt = "\n".join(parts)
    (HERE / "report.md").write_text(txt, encoding="utf-8")
    sys.stdout.buffer.write(txt.encode('utf-8'))
