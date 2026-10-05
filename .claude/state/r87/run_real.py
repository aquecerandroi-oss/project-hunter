"""R87 — H-028 no dado real.

    uv run --no-sync python .claude/state/r87/run_real.py counts   # cobertura e contagens de decisão (nenhum desfecho)
    uv run --no-sync python .claude/state/r87/run_real.py full     # protocolo inteiro → h028.txt
"""

from __future__ import annotations

import datetime as dt
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "r84"))
from analyze87 import (  # noqa: E402
    BOUNDS,
    CONVS,
    NAMES,
    SEED,
    by_year,
    episode_stats,
    max_dd,
    mondays,
    run,
    without_symbols,
)
from data87 import load_market  # noqa: E402
from engine87 import ARMS, C_PERP, C_SPOT, DAY_MS, H_MS, MIN_N, decide, s7, universe  # noqa: E402
from sim87 import simulate_arm  # noqa: E402
from stats84 import ci, mbb_indices  # noqa: E402

E = dt.date(1970, 1, 1)
FIRST_DAY = (dt.date(2019, 9, 9) - E).days
LAST_T = (dt.date(2026, 9, 14) - E).days


def iso(d: int) -> str:
    return (E + dt.timedelta(days=int(d))).isoformat()


def pct(x: float) -> str:
    return f"{100 * x:+.2f} %"


def decision_counts(mk, ts) -> list[str]:
    out = []
    syms = {mk.p.ids[i].split("#")[0] for t in ts for i in universe(mk, t)}
    out.append(f"semanas {len(ts)} ({iso(mk.p.day0 + ts[0])} → {iso(mk.p.day0 + ts[-1])}); símbolos distintos no "
               f"universo {len(syms)}; N_T médio {np.mean([len(universe(mk, t)) for t in ts]):.2f}; semanas com N_T < 15: "
               f"{sum(len(universe(mk, t)) < MIN_N for t in ts)}")
    for a in ("A1", "A2"):
        on: set[int] = set()
        entries, weeks = 0, set()
        for k, t in enumerate(ts):
            new = decide(mk, t, universe(mk, t), on, ARMS[a])
            ent = new - on
            entries += len(ent)
            weeks |= {k} if ent else set()
            on = new
        out.append(f"{a}: entradas pela regra (só decisão, sem liquidação/fim de série) {entries} em {len(weeks)} semanas")
    return out


def lookahead_real(mk, ts, n: int = 25) -> list[str]:
    rng = np.random.default_rng(SEED)
    sample = sorted(rng.choice(ts, size=n, replace=False).tolist())
    bad, bad_path = [], []
    for t in sample:
        t_day = mk.p.day0 + t
        cut, _ = load_market(cut_day=t_day, cut_funding_ms=t_day * DAY_MS - H_MS)
        tc = t_day - cut.p.day0
        ia, ib = universe(mk, t), universe(cut, tc)
        ua = [mk.p.ids[i].split("#")[0] for i in ia]  # sufixo #k vem de lacuna futura (convenção do R84)
        ub = [cut.p.ids[i].split("#")[0] for i in ib]
        sa = [s7(mk, i, t) for i in ia]
        sb = [s7(cut, i, tc) for i in ib] if ua == ub else []
        da = [sorted(decide(mk, t, ia, set(), ARMS[a])) for a in ("A1", "A2")]
        db = [sorted(decide(cut, tc, ib, set(), ARMS[a])) for a in ("A1", "A2")]
        da = [[mk.p.ids[i].split("#")[0] for i in x] for x in da]
        db = [[cut.p.ids[i].split("#")[0] for i in x] for x in db]
        if ua != ub or sa != sb or da != db:
            bad.append(iso(t_day))
        k = ts.index(t)
        if k >= 2:
            for a in ("A0", "A1", "A2"):
                fa = simulate_arm(mk, ts[: k - 1], ARMS[a], "pes", "after")
                fb = simulate_arm(cut, ts[: k - 1], ARMS[a], "pes", "after")
                if fa.open_at_end != fb.open_at_end or not np.allclose(fa.weekly, fb.weekly, rtol=0, atol=1e-15):
                    bad_path.append(f"{iso(t_day)} {a}")
    return [f"antecipação no dado real: {n} semanas reconstruídas só com velas < T e funding ≤ T − 1 h; "
            f"divergências de universo/S7/entradas A1-A2 (por símbolo, sem o sufixo #k): {bad if bad else 'nenhuma'}",
            f"trajetória (A0/A1/A2, pes/after) refeita com o dado cortado até a semana anterior a T — posições abertas e "
            f"P&L semanal idênticos: divergências {bad_path if bad_path else 'nenhuma'}"]


def report(mk, ts, out) -> list[str]:
    days = np.array(ts) + mk.p.day0
    L = [f"semanas {out['n_weeks']} ({iso(out['first'])} → {iso(out['last'])}), antes de 2023: {out['n_pre']}; "
         f"N_T médio {out['mean_n']:.2f}; semanas com N_T < 15 depois do início: {out['low_n_weeks']}"]
    L.append("## Veredito por braço (Holm sobre A0/A1/A2 em cada célula; rótulo exige as 4 células)")
    for a in NAMES:
        L.append(f"{a}: {out['verdicts'][a][0]} — {out['verdicts'][a][1]}")
    L.append("## Células (anualizado aritmético = 52 × média semanal sobre o capital total)")
    for b in BOUNDS:
        for c in CONVS:
            for a in NAMES:
                s = out["cells"][(b, c)][a]
                L.append(f"[{b}/{c}] {a}: {pct(s['ann'])} IC [{pct(s['lo'])}; {pct(s['hi'])}] p {s['p']:.4f} Holm "
                         f"{s['holm']:.4f} | antes 2023 {pct(s['pre'])} depois {pct(s['post'])} | patamar "
                         f"{', '.join(pct(v) for v in s['plat']) or '—'} | cobertura {s['cover']} | episódios "
                         f"{s['eps']} em {s['ep_weeks']} sem. | funding ausente {s['miss_frac']:.3%}")
    idx = mbb_indices(len(ts), 13, 10_000, SEED)
    for b in BOUNDS:
        sims = {a: out["sims"][(a, b, "after")] for a in NAMES}
        L.append(f"## Descritivo [{b}/after]")
        for a in NAMES:
            r = sims[a]
            ann = lambda x: 52 * float(np.mean(x))  # noqa: E731
            sd = float(np.std(r.weekly, ddof=1))
            L.append(f"{a}: funding {pct(ann(r.funding))} basis {pct(ann(r.basis))} à vista descoberta "
                     f"{pct(ann(r.unhedged))} custos {pct(-ann(r.costs))} liquidação {pct(ann(r.liq_loss))} = "
                     f"{pct(ann(r.weekly))}; exposição média {np.mean(r.exposure):.3f}; "
                     f"Sharpe {np.mean(r.weekly) / sd * np.sqrt(52) if sd > 0 else float('nan'):.2f}; DD máx "
                     f"{pct(max_dd(r.weekly))}; pior semana {pct(float(np.min(r.weekly)))}; liquidações {r.liquidations}; "
                     f"fim à vista {r.spot_ends}; fim perp {r.perp_ends}; presas {r.stuck}; guarda {r.guard_blocked}; "
                     f"marca ausente→negociado {r.mark_fallback}")
            yrs = by_year(r.weekly, days)
            L.append("   por ano: " + "; ".join(f"{y} {pct(v)} ({n} sem.)" for y, (v, n) in yrs.items()))
            ep = episode_stats(r)
            if ep["n"]:
                L.append(f"   episódios: n {ep['n']}, média {pct(ep['mean'])} da vaga, mediana {pct(ep['median'])}, "
                         f"> 0 em {ep['pos']:.0%}, IC por semana de entrada [{pct(ep['lo'])}; {pct(ep['hi'])}], "
                         f"duração média {ep['weeks']:.1f} sem., censurados {ep['censored']}")
            top = sorted(r.fund_by_symbol.items(), key=lambda kv: -kv[1])[:3]
            tot_f = sum(r.fund_by_symbol.values())
            L.append(f"   funding nas 3 maiores: {[k for k, _ in top]} = {sum(v for _, v in top) / tot_f:.0%} do funding" if tot_f else "   sem funding")
        for a in ("A1", "A2"):
            d = sims[a].weekly - sims["A0"].weekly
            lo, hi = ci(d, idx)
            L.append(f"{a} − A0: {pct(52 * float(np.mean(d)))} IC [{pct(52 * lo)}; {pct(52 * hi)}]")
    return L


def robustness(mk, ts, out) -> list[str]:
    L = ["## Robustez (não decide)"]
    for blk in (8, 26):
        idx = mbb_indices(len(ts), blk, 10_000, SEED)
        for a in NAMES:
            lo, hi = ci(out["sims"][(a, "pes", "after")].weekly, idx)
            L.append(f"blocos de {blk} sem. [pes/after] {a}: IC [{pct(52 * lo)}; {pct(52 * hi)}]")
    idx = mbb_indices(len(ts), 13, 10_000, SEED)
    for a in NAMES:
        r2 = simulate_arm(mk, ts, ARMS[a], "pes", "after", 2 * C_SPOT, 2 * C_PERP).weekly
        lo, hi = ci(r2, idx)
        L.append(f"custos dobrados [pes/after] {a}: {pct(52 * float(np.mean(r2)))} IC [{pct(52 * lo)}; {pct(52 * hi)}]")
    for a in NAMES:
        r = out["sims"][(a, "pes", "after")]
        top = [k for k, _ in sorted(r.fund_by_symbol.items(), key=lambda kv: -kv[1])[:3]]
        r3 = simulate_arm(without_symbols(mk, set(top)), ts, ARMS[a], "pes", "after").weekly
        lo, hi = ci(r3, idx)
        L.append(f"sem {top} [pes/after] {a}: {pct(52 * float(np.mean(r3)))} IC [{pct(52 * lo)}; {pct(52 * hi)}]")
    return L


def tails(mk, ts, out) -> list[str]:
    """Diagnóstico de cauda — NÃO pré-registrado, escrito depois de ver as liquidações (auditoria); não decide nada."""
    days = np.array(ts) + mk.p.day0
    post = days >= (dt.date(2023, 1, 1) - E).days
    y2021 = np.array([(E + dt.timedelta(days=int(d))).year == 2021 for d in days])
    L = ["## Diagnóstico de cauda (NÃO pré-registrado; depois de ver as liquidações; não decide)"]
    for a in NAMES:
        r = out["sims"][(a, "pes", "after")]
        n = len(ts)
        liq_net = sum(e["net"] for e in r.liq_events)
        top5 = np.sort(r.weekly)[-5:].sum()
        ann = lambda x: 52 * float(np.mean(x))  # noqa: E731
        wk = sorted({ts.index(e["t"]) for e in r.liq_events})
        whole = float(r.weekly[wk].sum()) if wk else 0.0
        L.append(f"{a}: resultado contabilizado das {len(r.liq_events)} vagas liquidadas (semana da liquidação, sem o custo "
                 f"de reajuste) {pct(52 * liq_net / n)} a.a.; subtraído, restam {pct(52 * (r.weekly.sum() - liq_net) / n)} "
                 f"(não é estratégia contrafactual sem liquidações); as {len(wk)} semanas inteiras com alguma liquidação "
                 f"somam {pct(52 * whole / n)} e o resto das semanas (mesmo denominador) {pct(52 * (r.weekly.sum() - whole) / n)}; "
                 f"5 melhores semanas = {pct(52 * top5 / n)} a.a.; sem 2021 "
                 f"{pct(ann(r.weekly[~y2021]))}; desde 2023: funding {pct(ann(r.funding[post]))} basis "
                 f"{pct(ann(r.basis[post]))} à vista descoberta {pct(ann(r.unhedged[post]))} custos "
                 f"{pct(-ann(r.costs[post]))} liquidação {pct(ann(r.liq_loss[post]))} "
                 f"= {pct(ann(r.weekly[post]))}")
    return L


def main(mode: str) -> None:
    t0 = time.time()
    mk, info = load_market()
    head = [f"# R87 — H-029 (registrada como H-028) no dado real (spot as_of 2026-09-28; T {iso(FIRST_DAY)} → {iso(LAST_T)})",
            f"séries à vista {len(mk.p.ids)}; com perpétuo mapeado {info['mapped']}; contratos com multiplicador "
            f"{info['multiplied']}; perpétuos com lacuna ≥ 14 d partidos {info['perp_segments_split']}; carregado em "
            f"{time.time() - t0:.0f} s"]
    ts = mondays(mk, FIRST_DAY, LAST_T)
    head += decision_counts(mk, ts)
    if mode == "counts":
        text = "\n".join(head) + "\n"
        (HERE / "counts.txt").write_text(text, encoding="utf-8")
        print(text)
        return
    out = run(mk, ts)
    body = report(mk, ts, out) + robustness(mk, ts, out) + tails(mk, ts, out) + lookahead_real(mk, ts)
    text = "\n".join(head + body + [f"tempo total {time.time() - t0:.0f} s"]) + "\n"
    (HERE / "h029.txt").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main(sys.argv[1])
