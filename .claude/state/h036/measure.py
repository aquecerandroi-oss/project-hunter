"""h036 — mede o instrumento de custo na coorte EXPOSTA (os desfechos que o lab-cost-sweep já leu; nada depois do
corte de 2026-10-07 06:07Z). Diagnóstico: nenhum rótulo sai daqui. Saída em measure.txt.

uv run --no-sync python .claude/state/h036/measure.py > .claude/state/h036/measure.txt
"""

from __future__ import annotations

import csv
import gzip
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "lab-cost-sweep"))

import cost_instrument as ci  # noqa: E402
import sweep  # noqa: E402


def _f(x: str) -> float | None:
    return None if x is None or x.strip() == "" else float(x)


def load() -> list[tuple[sweep.Trade, dict[str, str]]]:
    trades = {r["signal_id"]: sweep.Trade.from_row(r)
              for r in csv.DictReader(gzip.open(HERE.parent / "lab-cost-sweep/cache/out.csv.gz", "rt", encoding="utf-8"))}
    cost = list(csv.DictReader(open(HERE / "cache/cost.csv", encoding="utf-8")))
    return [(trades[c["signal_id"]], c) for c in cost]


def build(pairs: list[tuple[sweep.Trade, dict[str, str]]]) -> list[tuple[sweep.Trade, ci.Legs, dict[str, object]]]:
    obs_by_mkt: dict[str, list[float]] = defaultdict(list)
    allobs: list[float] = []
    for t, c in pairs:
        for k in ("sp_in", "sp_out"):
            v = _f(c[k])
            if v is not None:
                obs_by_mkt[t.symbol].append(v)
                allobs.append(v)
    med = {m: float(np.median(v)) for m, v in obs_by_mkt.items()}
    p90 = float(np.percentile(allobs, 90))
    out = []
    for t, c in pairs:
        s_in, o_in = ci.pick_spread(_f(c["sp_in"]), (_f(c["sp_in_m1"]), _f(c["sp_in_p1"])),
                                    market_median=med.get(t.symbol), cohort_p90=p90)
        s_out, o_out = ci.pick_spread(_f(c["sp_out"]), (_f(c["sp_out_p1"]),),
                                      market_median=med.get(t.symbol), cohort_p90=p90)
        s_out_stress = max(v for v in (s_out, _f(c["sp_out_p1"])) if v is not None)
        tick = ci.tick_of(tuple(c[k] for k in ("x_high", "c0_open", "c0_low", "c1_low", "c2_low", "bid_in", "ask_in")))
        legs = ci.Legs(open=t.open, base=t.base, risk=t.risk, result=c["result"], exit_at_open=c["x_at_open"] == "t",
                       exit_high=_f(c["x_high"]), target1=ci.limit_at_or_above(float(c["target1"]), tick),
                       sp_in=s_in, sp_out=s_out,
                       bid_in=_f(c["bid_in"]), entry_lows=(_f(c["c0_low"]), _f(c["c1_low"]), _f(c["c2_low"])))
        out.append((t, legs, {"o_in": o_in, "o_out": o_out, "s_out_stress": s_out_stress}))
    return out


def scen_costs(legs: ci.Legs, extra: dict[str, object]) -> dict[str, float]:
    def cr(c: tuple[float, float]) -> float:
        return ci.cost_r(open_=legs.open, base=legs.base, risk=legs.risk, c_in=c[0], c_out=c[1])
    tt = ci.taker_taker(legs)
    stress = (tt[0] + 2 * ci.BP, ci.TAKER + float(extra["s_out_stress"]) / 2 + 2 * ci.BP)  # type: ignore[arg-type]
    return {
        "lab20": cr((10 * ci.BP, 10 * ci.BP)),
        "taker_fee_only": cr((ci.TAKER, ci.TAKER)),
        "A_taker": cr(tt),
        "A_stress": cr(stress),
        "B_tp_strict": cr(ci.taker_in_resting_tp(legs, strict=True)),
        "B_tp_touch": cr(ci.taker_in_resting_tp(legs, strict=False)),
    }


def q(v: np.ndarray) -> str:
    return f"p50 {np.median(v):.2f} · média {v.mean():.2f} · p90 {np.percentile(v, 90):.2f} · p99 {np.percentile(v, 99):.2f}"


def report(name: str, rows: list[tuple[sweep.Trade, ci.Legs, dict[str, object]]]) -> None:
    rows = [r for r in rows if r[0].funding is not None]
    if len(rows) < 20:
        return
    ts = [r[0] for r in rows]
    days = [t.day for t in ts]
    mkts = [t.symbol for t in ts]
    g = np.array([t.gross_r for t in ts])
    phi = np.array([t.funding_r for t in ts], dtype=float)
    h = np.array([t.notional_per_r for t in ts])
    one = np.ones(len(ts))
    print(f"\n## {name} — n {len(ts)} (com funding), {len(set(days))} dias, {len(set(mkts))} mercados")
    oi = defaultdict(int); oo = defaultdict(int)
    for _, _, e in rows:
        oi[e["o_in"]] += 1; oo[e["o_out"]] += 1
    print(f"origem do spread — entrada {dict(oi)} · saída {dict(oo)}")
    sin = np.array([lg.sp_in for _, lg, _ in rows]) / ci.BP
    sout = np.array([lg.sp_out for _, lg, _ in rows]) / ci.BP
    print(f"spread cotado (bp) — entrada: {q(sin)}")
    print(f"                    saída:   {q(sout)}")
    by_res = defaultdict(list)
    for (_, lg, _), s in zip(rows, sout):
        by_res[lg.result].append(s)
    print("spread na saída por motivo (p50/p90 bp, n): " + " · ".join(
        f"{k} {np.median(v):.2f}/{np.percentile(v, 90):.2f} ({len(v)})" for k, v in sorted(by_res.items())))
    kstar = sweep.ratio_ci(g - phi, h, days, scale=2e4)
    print(f"k* (bp, IC dia) {kstar[0]:+.1f} [{kstar[1]:+.1f}; {kstar[2]:+.1f}] · bruto G {g.mean():+.3f}")
    costs = [scen_costs(lg, e) for _, lg, e in rows]
    print("| cenário | custo efetivo bp | custo médio R | margem k*−efetivo bp [IC dia] | R médio [IC dia] [IC mercado] |")
    print("|---|---|---|---|---|")
    for sc in costs[0]:
        cr = np.array([c[sc] for c in costs])
        eff = ci.effective_cost_bp(cr, h)
        net = ci.net_r(g, phi, cr)
        m = sweep.ratio_ci(net, h, days, scale=2e4)
        rd = sweep.ratio_ci(net, one, days)
        rm = sweep.ratio_ci(net, one, mkts)
        print(f"| {sc} | {eff:.2f} | {cr.mean():.3f} | {m[0]:+.1f} [{m[1]:+.1f}; {m[2]:+.1f}] | "
              f"{rd[0]:+.3f} [{rd[1]:+.3f}; {rd[2]:+.3f}] [{rm[1]:+.3f}; {rm[2]:+.3f}] |")
    # C: entrada passiva no bid do minuto (executa só se a mínima da vela atravessar o bid em 1 min), alvo em repouso
    # estrito, stop/expiração a mercado; sinal não executado = trade que não houve (0). Desconhecido conta como não.
    fills = np.array([bool(ci.passive_fill(bid=lg.bid_in, lows=lg.entry_lows, minutes=1)) for _, lg, _ in rows])
    c_in = np.array([ci.passive_entry_cost(bid=lg.bid_in, open_=lg.open) if lg.bid_in is not None else np.nan
                     for _, lg, _ in rows])
    c_out = np.array([ci.taker_in_resting_tp(lg, strict=True)[1] for _, lg, _ in rows])
    crc = np.array([ci.cost_r(open_=lg.open, base=lg.base, risk=lg.risk, c_in=a, c_out=b)
                    for (_, lg, _), a, b in zip(rows, c_in, c_out)])
    netc = ci.passive_signal_r(ci.net_r(g, phi, np.nan_to_num(crc)), fills)
    rd = sweep.ratio_ci(netc, one, days)
    eff = ci.effective_cost_bp(crc[fills], h[fills])
    print(f"| C_passive_1m (executa {fills.sum()}/{len(fills)}) | {eff:.2f} (executados) | {crc[fills].mean():.3f} | — | "
          f"{rd[0]:+.3f} por sinal [{rd[1]:+.3f}; {rd[2]:+.3f}]; por trade executado {netc[fills].mean():+.3f} |")
    tgt = [lg for _, lg, _ in rows if lg.result == "target"]
    touch = sum(1 for lg in tgt if not lg.exit_at_open and lg.exit_high is not None and lg.exit_high <= lg.target1)
    print(f"alvos {len(tgt)}: só tocaram o limite no grid (máxima ≤ alvo no passo de preço) {touch}; "
          f"abertura acima {sum(lg.exit_at_open for lg in tgt)}")
    for mins in (1, 2, 3):
        fills = [ci.passive_fill(bid=lg.bid_in, lows=lg.entry_lows, minutes=mins) for _, lg, _ in rows]
        known = [i for i, f in enumerate(fills) if f is not None]
        fi = [i for i in known if fills[i]]
        ui = [i for i in known if not fills[i]]
        if not fi or not ui:
            continue
        pe = np.array([ci.passive_entry_cost(bid=rows[i][1].bid_in, open_=rows[i][1].open) for i in fi])  # type: ignore[arg-type]
        print(f"entrada passiva no bid, {mins} min: conhecidos {len(known)}, executa {len(fi)} ({len(fi)/len(known):.0%}); "
              f"custo da perna passiva p50 {np.median(pe)/ci.BP:+.2f} bp; bruto G executados {g[fi].mean():+.3f} × "
              f"não executados {g[ui].mean():+.3f} (seleção adversa, descritivo; G mede da abertura, não do bid)")


def main() -> None:
    rows = build(load())
    groups: dict[str, list] = defaultdict(list)
    for r in rows:
        groups[f"{r[0].strategy} {r[0].version}"].append(r)
    fam = [r for r in rows if r[0].strategy == "mean_reversion"]
    order = ["mean_reversion v14", "mean_reversion v6", "mean_reversion v7", "mean_reversion v10",
             "mean_reversion v1", "mean_reversion v2", "mean_reversion v3", "mean_reversion v8", "momentum v3"]
    print("h036 — instrumento de custo na coorte EXPOSTA (lab-cost-sweep 2026-10-07 06:07Z); diagnóstico, sem rótulo")
    print("taxas: taker 5 bp, maker 2 bp por perna (VIP 0, sem BNB; suposição); lab20 = custo assumido do Lab (10 bp/perna)")
    for name in order:
        report(name, groups[name])
    report("família mean_reversion (todas as versões; entradas repetidas entre versões)", fam)


if __name__ == "__main__":
    main()
