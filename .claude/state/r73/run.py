"""R73 — cobertura, contraste de tercis, cauda e contrafactual do teto de concentração.

Roda o moinho (`infra.research.run_hypothesis`) no contraste tercil alto × tercil baixo
(o meio é retirado, e o limiar congelado cai na fronteira) e faz, fora do moinho, as duas
contas que a H-010 pede e que ele não sabe fazer: a **cauda** (fração de posições com
perda ≥ 50 %) e o **contrafactual** do teto sobre as posições reais.
"""

from __future__ import annotations

import csv
import statistics
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from build import build, one_per_mint  # noqa: E402
from load import concentration, load_population, load_tape  # noqa: E402

from infra.research.protocol import run_hypothesis  # noqa: E402
from infra.research.report import render  # noqa: E402
from infra.research.spec import (  # noqa: E402
    DecisionPolicy,
    HypothesisSpec,
    InferencePlan,
    ObservabilityWaiver,
    PreRegistration,
)

HERE = Path(__file__).resolve().parent
PRE = PreRegistration(
    prediction=(
        "decisões com maior_comprador_pct no tercil alto rendem menos −0,05 por SOL que "
        "o tercil baixo — isto é, comprar onde um dono concentra o estoque é pior"
    ),
    refutation=(
        "limite inferior do IC 95 % (bootstrap por mint) acima de −0,01 por SOL; ou "
        "cobertura da fita desde o nascimento < 60 % da população (sem fita completa não "
        "dá para medir o maior comprador, e isso é limite de dado, não resultado)"
    ),
    decision_rule=(
        "CONFIRMA com D>0 (baixo−alto), IC inferior>0, p<0,05, D≥MRE, braço selecionado "
        "lucrativo em nível e planalto. Sinal espelhado: o bloco escreve o contraste "
        "alto−baixo, o moinho corre baixo−alto (direction='low')."
    ),
    registered_on="2026-09-23",
    threshold_policy="tercis da amostra elegível, fixados antes de olhar desfechos",
)
GRID = (0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50)


def _f(x: object) -> float | None:
    try:
        return float(str(x))
    except (TypeError, ValueError):
        return None


def retro_pct(rows: list[dict[str, object]]) -> None:
    """Acrescenta `pct_retro`: a mesma variável com a fita **completa de hoje**.

    Não é uma feature — é o oráculo. Serve só para o contrafactual e está rotulado como
    tal em todo o relatório: no instante da decisão nós não tínhamos esta fita.
    """
    tape = load_tape()
    pop = {p["bet_id"]: p for p in load_population()}
    for r in rows:
        p = pop[str(r["bet_id"])]
        c = concentration(tape.get(str(r["mint"]), []), p["decided_at"], guard=False)  # type: ignore[arg-type]
        r["pct_retro"] = c.pct
        r["pct_retro_estoque"] = c.pct_estoque
        r["pct_retro_bruto"] = c.pct_bruto
        r["curve_retro_sol"] = c.curve_sol
        r["top_retro"] = c.top_wallet
        r["top_retro_is_creator"] = c.top_wallet is not None and c.top_wallet == p["creator"]


def cobertura(rows: list[dict[str, object]]) -> str:
    out = ["| recorte | n | fita começa no nascimento | reconcilia com a foto | **nasce E reconcilia** "
           "| elegível p/ contraste com guarda (+ pct observável) |",
           "|---|---:|---:|---:|---:|---:|"]
    for label, sub in (
        ("posições reais", [r for r in rows if r["lane"] == "live"]),
        ("apostas de papel", [r for r in rows if r["lane"] == "paper"]),
        ("uma por mint", one_per_mint(rows)),
    ):
        n = len(sub)
        nasce = sum(1 for r in sub if r["nasce"] == "True" or r["nasce"] is True)
        rec = sum(1 for r in sub if r["cov_retro"] == "True" or r["cov_retro"] is True)
        el = sum(1 for r in sub if r["elegivel"] == "True" or r["elegivel"] is True)
        both = sum(1 for r in sub if r["nasce"] is True and r["cov_retro"] is True)
        out.append(
            f"| {label} | {n} | {nasce} ({nasce / n:.1%}) | {rec} ({rec / n:.1%}) "
            f"| **{both} ({both / n:.1%})** | {el} ({el / n:.1%}) |"
        )
    return "\n".join(out)


def terciles(vals: list[float]) -> tuple[float, float]:
    v = sorted(vals)
    return v[len(v) // 3], v[2 * len(v) // 3]


def tabela_tercis(sub: list[dict[str, object]], var: str) -> str:
    vals = [_f(r[var]) for r in sub]
    xs = [v for v in vals if v is not None]
    lo, hi = terciles(xs)
    bands = {"baixo": [], "meio": [], "alto": []}  # type: dict[str, list[dict[str, object]]]
    for r in sub:
        v = _f(r[var])
        if v is None:
            continue
        bands["baixo" if v < lo else ("alto" if v >= hi else "meio")].append(r)
    out = [
        f"Cortes dos tercis de `{var}`: baixo < {lo:.3f} ≤ meio < {hi:.3f} ≤ alto",
        "",
        "| tercil | n | mediana da variável | ret médio (SOL/SOL) | mediana | "
        "**cauda: perda ≥ 50 %** | vitórias > 0 | PnL total (SOL) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ("baixo", "meio", "alto"):
        b = bands[name]
        rets = [_f(r["ret"]) for r in b]
        rets = [x for x in rets if x is not None]
        tail = sum(1 for x in rets if x <= -0.50)
        wins = sum(1 for x in rets if x > 0)
        pnl = sum((Decimal(str(r["pnl_sol"])) for r in b if r["pnl_sol"]), Decimal(0))
        med_v = statistics.median([_f(r[var]) for r in b])  # type: ignore[arg-type]
        out.append(
            f"| {name} | {len(b)} | {med_v:.3f} | {statistics.mean(rets):+.4f} | "
            f"{statistics.median(rets):+.4f} | **{tail} ({tail / len(b):.1%})** | "
            f"{wins} ({wins / len(b):.1%}) | {pnl:+.4f} |"
        )
    return "\n".join(out), bands, (lo, hi)  # type: ignore[return-value]


def contrafactual(live: list[dict[str, object]], var: str) -> str:
    rets = [(_f(r[var]), _f(r["ret"]), Decimal(str(r["pnl_sol"])), r) for r in live]
    total = sum((x[2] for x in rets), Decimal(0))
    out = [
        f"Base: {len(live)} posições reais, PnL total **{total:+.4f} SOL**. "
        f"Variável: `{var}`.",
        "",
        "| teto | bloqueadas | das quais VENCEDORAS | PnL removido | PnL que sobra | "
        "Δ vs hoje | mede? |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for ceil in GRID:
        blocked = [x for x in rets if x[0] is not None and x[0] > ceil]
        winners = [x for x in blocked if x[1] is not None and x[1] > 0]
        removed = sum((x[2] for x in blocked), Decimal(0))
        rest = total - removed
        n_meas = sum(1 for x in rets if x[0] is not None)
        out.append(
            f"| > {ceil:.0%} | {len(blocked)} | **{len(winners)}** | {removed:+.4f} | "
            f"{rest:+.4f} | {rest - total:+.4f} | {n_meas}/{len(live)} |"
        )
    return "\n".join(out)


def moinho(bands: dict, cuts: tuple[float, float], var: str) -> str:
    extremos = [dict(r) for r in bands["baixo"] + bands["alto"]]
    for r in extremos:
        r[var] = _f(r[var])
        r["ret"] = _f(r["ret"])
        r["pnl_sol"] = Decimal(str(r["pnl_sol"]))
    spec = HypothesisSpec(
        name="H-010 — concentração do maior comprador (tercil alto × tercil baixo)",
        origin="perda real AIRAA 23/09/2026 17:03 BRT; max_top10_share vazio nas duas mesas",
        loader=lambda: extremos,
        decision_instant="decided_at",
        outcome="ret",
        variable=var,
        direction="low",
        observability=ObservabilityWaiver(
            reason=(
                "a guarda da T4.80 corre dentro do carregador (`load.concentration`, "
                "`received_at <= decisão`), não nas colunas do moinho; e o contrafactual "
                "usa de propósito a fita retrospetiva, declarada como oráculo"
            )
        ),
        inference=InferencePlan(
            cluster="mint", stratum="dia", block="hora",
            thresholds=GRID, reps=10_000, seed=73,
        ),
        # o moinho seleciona `var <= limiar` (direction='low'); o limiar é o maior valor do
        # tercil baixo, para que baixo × alto fique exato (achado da Astra: com `hi` uma
        # linha do alto caía no baixo — 188/187 em vez de 187/188)
        policy=DecisionPolicy(
            frozen_threshold=max(float(r[var]) for r in bands["baixo"]), minimum_effect=0.05
        ),
        pre_registration=PRE,
        money_column="pnl_sol",
        assumptions=(
            "ficha de 0,05–0,07 SOL; custo de ida-e-volta já dentro do pnl persistido",
            "desfecho = pnl_sol / tamanho, sob a saída que cada mesa realmente usou",
        ),
    )
    return render(run_hypothesis(spec))


if __name__ == "__main__":
    rows = build()
    retro_pct(rows)
    for r in rows:
        r["nasce"] = bool(r["nasce"])
        r["cov_retro"] = bool(r["cov_retro"])
        r["elegivel"] = bool(r["elegivel"])
    parts = ["## 1. Cobertura\n", cobertura(rows), ""]

    el = [r for r in one_per_mint(rows) if r["elegivel"] and _f(r["pct"]) is not None]
    parts += [f"\n## 2. Tercis — população elegível, variável medida com a guarda (n={len(el)})\n"]
    tab, bands, cuts = tabela_tercis(el, "pct")  # type: ignore[misc]
    parts += [tab, ""]

    todos = [r for r in one_per_mint(rows) if _f(r["pct_retro"]) is not None and _f(r["ret"]) is not None]
    parts += [f"\n## 3. Tercis — fita retrospetiva (ORÁCULO, não era nossa na decisão) n={len(todos)}\n"]
    tab2, bands2, cuts2 = tabela_tercis(todos, "pct_retro")  # type: ignore[misc]
    parts += [tab2, ""]

    parts += ["\n## 3b. Sensibilidade — compras BRUTAS (a letra da fila), fita retrospetiva\n"]
    parts += [tabela_tercis(todos, "pct_retro_bruto")[0], ""]
    parts += ["\n## 3c. Sensibilidade — ESTOQUE de tokens, fita retrospetiva\n"]
    est = [r for r in todos if _f(r["pct_retro_estoque"]) is not None]
    parts += [tabela_tercis(est, "pct_retro_estoque")[0], ""]

    live = [r for r in rows if r["lane"] == "live" and r["pnl_sol"]]
    parts += ["\n## 4. Contrafactual do teto — posições reais, variável OBSERVÁVEL na decisão\n"]
    parts += [contrafactual(live, "pct"), ""]
    parts += ["\n## 5. Contrafactual do teto — posições reais, fita retrospetiva (oráculo)\n"]
    parts += [contrafactual(live, "pct_retro"), ""]

    parts += ["\n## 6. Moinho — tercil alto × tercil baixo, fita retrospetiva\n"]
    try:
        parts += [moinho(bands2, cuts2, "pct_retro")]
    except Exception as exc:  # noqa: BLE001
        parts += [f"moinho recusou correr: `{type(exc).__name__}: {exc}`"]

    txt = "\n".join(parts)
    (HERE / "report.md").write_text(txt, encoding="utf-8")
    with (HERE / "rows_retro.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(txt)
