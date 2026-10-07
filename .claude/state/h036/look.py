"""h036 — a consulta: desfechos (gen_look.py) + exports cegos de spread (gen_export2.py) → R primário e de estresse por
trade → cobertura → ``decision.decide``. A mesma função de decisão da simulação (run_design2.py).

uv run --no-sync python .claude/state/h036/look.py <look 0|1|2> <desfechos.csv> <export1.csv[.gz]> [...]
"""

from __future__ import annotations

import csv
import gzip
import sys
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "lab-cost-sweep"))

import decision as dc  # noqa: E402
import sweep  # noqa: E402

BP = 1e-4
TAKER = 5 * BP
T0_DATE = date(2026, 10, 7)
MED_MIN = 5040  # mediana de 7 d só vale com ≥ 50 % dos 10 080 minutos
MIN = timedelta(minutes=1)


def leg_spread(series: dict[datetime, float], at: datetime, *, med: tuple[float | None, int], p90: float
               ) -> tuple[float, str]:
    if at in series:
        return series[at], "minuto"
    for nb in (at - MIN, at + MIN):
        if nb in series:
            return series[nb], "vizinho"
    if med[0] is not None and med[1] >= MED_MIN:
        return med[0], "mediana_7d"
    return p90, "p90"


def trade_r(*, open_: float, base: float, risk: float, funding: float, sp_in: float, sp_out: float,
            sp_out_next: float) -> tuple[float, float]:
    """(R primário todo a mercado, R de estresse) — taker 5 bp + meio spread; estresse: pior spread de saída, +2 bp."""
    g = (base - open_) / risk - funding / risk
    prim = ((TAKER + sp_in / 2) * open_ + (TAKER + sp_out / 2) * base) / risk
    stress = ((TAKER + sp_in / 2 + 2 * BP) * open_ + (TAKER + max(sp_out, sp_out_next) / 2 + 2 * BP) * base) / risk
    return g - prim, g - stress


def day_index(ts: datetime, base: date = T0_DATE) -> int:
    return (ts.astimezone(UTC).date() - base).days


def robust_label(orig: int, alt: int, *, final: bool = True) -> int:
    """Emenda: se o rótulo muda com os spreads substitutos no p99 da consulta, CONFIRMA/REFUTA não se sustentam —
    vira NÃO CONFIRMA na final e "continua" numa intermediária."""
    if orig == dc.CONFIRMA and alt != orig:
        return dc.NAO_CONFIRMA if final else dc.CONTINUA  # adiar eficácia é seguro (união de Bonferroni)
    if orig == dc.REFUTA and alt != orig:
        return dc.NAO_CONFIRMA  # nunca adiar uma parada por futilidade: daria novas chances de REFUTA
    return orig


def next_spread(series: dict[datetime, float], exit_minute: datetime, *, p90: float) -> tuple[float, str]:
    """Spread do minuto seguinte à saída para o estresse: +1 min → +2 min → p90 da consulta (conservador)."""
    for k, label in ((1, "+1 min"), (2, "+2 min")):
        v = series.get(exit_minute + k * MIN)
        if v is not None:
            return v, label
    return p90, "p90"


def daily(days: np.ndarray, prim: np.ndarray, stress: np.ndarray, *, n_days: int
          ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    c = np.bincount(days, minlength=n_days).astype(float)[None, :]
    s = np.bincount(days, weights=prim, minlength=n_days)[None, :]
    t = np.bincount(days, weights=stress, minlength=n_days)[None, :]
    return c, s, t


def _ts(x: str) -> datetime:
    return sweep._ts(x)  # noqa: SLF001 — o mesmo parser do lab-cost-sweep (recusa instante sem fuso)


def load_exports(paths: list[str]) -> tuple[dict[str, dict[datetime, float]], dict[str, tuple[float | None, int]]]:
    ser: dict[str, dict[datetime, float]] = defaultdict(dict)
    med: dict[str, tuple[float | None, int]] = {}
    for p in paths:
        fh = gzip.open(p, "rt", encoding="utf-8") if p.endswith(".gz") else open(p, encoding="utf-8")
        for r in csv.DictReader(fh):
            if r["tipo"] == "serie" and r["spread_pct"]:
                ser[r["signal_id"]][_ts(r["ts"])] = float(r["spread_pct"])
            elif r["tipo"] == "mediana_7d":
                med[r["signal_id"]] = (float(r["mediana_7d"]) if r["mediana_7d"] else None, int(r["n_snap_7d"] or 0))
    return ser, med


def main() -> None:
    look_k, out_csv, exports = int(sys.argv[1]), sys.argv[2], sys.argv[3:]
    rows = list(csv.DictReader(open(out_csv, encoding="utf-8")))
    ser, med = load_exports(exports)
    eligible = [r for r in rows if r["tracking_state"] != "no_entry"]
    trades = [r for r in eligible if r["tracking_state"] == "terminal" and r["funding_per_unit"]]
    states = defaultdict(int)
    for r in rows:
        key = r["tracking_state"] if r["tracking_state"] != "terminal" or r["funding_per_unit"] else "terminal_sem_funding"
        states[key] += 1
    print(f"estados: {dict(states)}")
    if not trades:
        print("nenhum trade avaliável → " + ("LIMITE (dado)" if look_k == 2 else "continua"))
        return
    sem_export = sum(1 for r in trades if r["signal_id"] not in med)
    print(f"trades sem linha no export cego (o export complementar da consulta deveria zerar isto): {sem_export}")
    observed = []  # pernas MEDIDAS (minuto ou vizinho) — base do p90/p99 (Astra rodada 2)
    for r in trades:
        for at in (_ts(r["entry_ts"]), _ts(r["xbo"])):
            got = leg_spread(ser[r["signal_id"]], at, med=(None, 0), p90=float("nan"))
            if got[1] in ("minuto", "vizinho"):
                observed.append(got[0])
    p90 = float(np.percentile(observed, 90)) if observed else float("nan")
    base = min(T0_DATE, min(_ts(r["emitted_at"]).date() for r in trades))  # ensaio na coorte exposta começa antes
    p99 = float(np.percentile(observed, 99)) if observed else float("nan")

    def build(sub_value: float | None) -> tuple[np.ndarray, np.ndarray, list[tuple[str, str]]]:
        prim, stress, origins = [], [], []
        for r in trades:
            c_bp = float(r["spread_bps"]) / 2 + float(r["slippage_bps"])
            entry_c, stop = float(r["entry_c"]), float(r["stop"])
            sid, xbo = r["signal_id"], _ts(r["xbo"])
            m7 = med.get(sid, (None, 0))
            s_in, o_in = leg_spread(ser[sid], _ts(r["entry_ts"]), med=m7, p90=p90)
            s_out, o_out = leg_spread(ser[sid], xbo, med=m7, p90=p90)
            if sub_value is not None:  # pernas sem medida (mediana/p90) levadas ao p99 da consulta
                s_in = sub_value if o_in in ("mediana_7d", "p90") else s_in
                s_out = sub_value if o_out in ("mediana_7d", "p90") else s_out
            s_next = next_spread(ser[sid], xbo, p90=p90)[0]
            p, st = trade_r(open_=entry_c / (1 + c_bp * BP), base=float(r["exit_base"]), risk=entry_c - stop,
                            funding=float(r["funding_per_unit"]), sp_in=s_in, sp_out=s_out, sp_out_next=s_next)
            prim.append(p); stress.append(st); origins.append((o_in, o_out))
        return np.array(prim), np.array(stress), origins

    pa, sa, origins = build(None)
    da = np.array([day_index(_ts(r["emitted_at"]), base) for r in trades])
    mkts = [r["symbol"] for r in trades]
    reasons = [r["result"] for r in trades]
    wo = base.weekday()
    measured = np.mean([a in ("minuto", "vizinho") and b in ("minuto", "vizinho") for a, b in origins])
    excluded = (len(eligible) - len(trades)) / max(len(eligible), 1)
    ok = np.array([excluded <= 0.05 and measured >= 0.90])
    c, s, t = daily(da, pa, sa, n_days=int(da.max()) + 1)
    v = int(dc.decide(c, s, t, look=look_k, coverage_ok=ok, week_offset=wo)[0])
    m, se, g = dc.stats(c, s, week_offset=wo)
    nsub = sum(1 for o in origins if o[0] in ("mediana_7d", "p90") or o[1] in ("mediana_7d", "p90"))
    if nsub:
        pa2, sa2, _ = build(p99)
        c2, s2, t2 = daily(da, pa2, sa2, n_days=int(da.max()) + 1)
        v2 = int(dc.decide(c2, s2, t2, look=look_k, coverage_ok=ok, week_offset=wo)[0])
        v = robust_label(v, v2, final=look_k == 2)
    print(f"consulta L{look_k + 1}: elegíveis {len(eligible)}, trades {len(trades)}, excluídos {excluded:.1%}, "
          f"custo medido nas duas pernas {measured:.1%}, substitutos {nsub}, dias {int((c > 0).sum())}, "
          f"semanas {int(g[0])}")
    print(f"R médio primário (todo a mercado, custo medido) {m[0]:+.4f} · EP semanal {se[0]:.4f} · t {m[0] / se[0]:.2f} · "
          f"estresse {sa.mean():+.4f} → {dc.NOMES[v]}")
    by = defaultdict(list)
    for mk, x in zip(mkts, pa):
        by[mk].append(x)
    top = max(by, key=lambda k: sum(by[k]))
    keep = np.array([mk != top for mk in mkts])
    print(f"sem o maior mercado ({top}): {pa[keep].mean():+.4f} · IC mercado {sweep.ratio_ci(pa, np.ones(len(pa)), mkts)}")
    for res in sorted(set(reasons)):
        sel = np.array([x == res for x in reasons])
        print(f"  {res}: n {int(sel.sum())}, R {pa[sel].mean():+.3f}")


if __name__ == "__main__":
    main()
