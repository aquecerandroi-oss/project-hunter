"""lab-cost-sweep — relatório: R bruto, R do Lab, custo de equilíbrio, cenários de custo realistas, meses, duração.

Diagnóstico, NÃO hipótese: nenhum rótulo CONFIRMA/REFUTA sai daqui. Os desfechos ficam EXPOSTOS.
Rodar: uv run python .claude/state/lab-cost-sweep/run.py > .claude/state/lab-cost-sweep/results.txt
"""

from __future__ import annotations

import csv
import gzip
import sys
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import sweep  # noqa: E402

MIN_N, MIN_DAYS, MIN_MKTS = 20, 5, 10  # IC por dia exige ≥ 5 dias; IC por mercado exige ≥ 10 mercados
# (nome, taxa por perna bp, slippage por perna bp, com funding?) — taxa fora dos preços; slippage nos preços.
SCENARIOS = (
    ("perp_taker_5", 5.0, 0.0, True),
    ("perp_taker_5+slip_2", 5.0, 2.0, True),
    ("perp_maker_2", 2.0, 0.0, True),
    ("perp_maker_0", 0.0, 0.0, True),
    ("perp_rebate_-0.5", -0.5, 0.0, True),
    ("spot_taker_10", 10.0, 0.0, False),
)


def load() -> list[sweep.Trade]:
    with gzip.open(HERE / "cache" / "out.csv.gz", "rt", encoding="utf-8") as fh:
        return [sweep.Trade.from_row(r) for r in csv.DictReader(fh)]


def group_key(t: sweep.Trade) -> tuple[str, str, str, str]:
    cohort = "prosp" if t.cohort == "prospective" else "replay:" + t.cohort.split(":", 1)[1][:8]
    return (t.strategy, t.version, t.mt, cohort)


def fmt_ci(est: float, lo: float, hi: float, nd: int = 3) -> str:
    return f"{est:+.{nd}f} [{lo:+.{nd}f}; {hi:+.{nd}f}]"


def funded(ts: Sequence[sweep.Trade]) -> list[sweep.Trade]:
    return [t for t in ts if t.funding is not None]


def _cis(out: dict[str, object], prefix: str, ts: list[sweep.Trade], num: np.ndarray, den: np.ndarray,
         scale: float = 1.0) -> None:
    """IC por dia (≥ 5 dias) e por mercado (≥ 10 mercados), cada um só se o seu piso for atingido."""
    clusters = {"day": [t.day for t in ts], "mkt": [t.symbol for t in ts]}
    floors = {"day": MIN_DAYS, "mkt": MIN_MKTS}
    for c in ("day", "mkt"):
        if len(ts) >= MIN_N and len(set(clusters[c])) >= floors[c]:
            out[f"{prefix}_{c}"] = sweep.ratio_ci(num, den, clusters[c], scale=scale)


def _sc_cluster(ts: list[sweep.Trade]) -> str | None:
    if len(ts) < MIN_N:
        return None
    if len({t.day for t in ts}) >= MIN_DAYS:
        return "day"
    return "mkt" if len({t.symbol for t in ts}) >= MIN_MKTS else None


def summary(key: tuple[str, ...], ts: list[sweep.Trade]) -> dict[str, object]:
    """Duas populações, cada uma com as suas contagens (Astra, must-fix 2): TODOS os terminais (bruto, cenário sem
    funding) e os COM funding estabelecido (R do Lab, Φ, k*, cenários com funding)."""
    act = sweep.activity(ts)
    out: dict[str, object] = {"key": "/".join(key), "spot": key[2] == "spot", **act}
    g_all = np.array([t.gross_r for t in ts])
    h_all = np.array([t.notional_per_r for t in ts])
    out.update(G_all=float(g_all.mean()), kstar_ex_all=sweep.break_even_bp(g_all, h_all))
    _cis(out, "Gall", ts, g_all, np.ones(len(ts)))
    sc_all = _sc_cluster(ts)
    if sc_all:
        r = np.array([t.scenario_r(fee_bp=10.0, slip_bp=0.0, with_funding=False) for t in ts], dtype=float)
        out["sc_all_cluster"] = sc_all
        out["sc_spot_taker_10"] = sweep.ratio_ci(r, np.ones(len(ts)), [getattr(t, sc_all if sc_all == "day"
                                                                             else "symbol") for t in ts])
    fts = funded(ts)
    out.update(n_f=len(fts), days_f=len({t.day for t in fts}), mk_f=len({t.symbol for t in fts}))
    if not fts:
        return out
    g = np.array([t.gross_r for t in fts])
    phi = np.array([t.funding_r for t in fts], dtype=float)
    h = np.array([t.notional_per_r for t in fts])
    # perpétuo: r_multiple gravado; spot: r_multiple é nulo → R líquido reconstruído sem funding (r_ex_funding)
    lab = np.array([t.r_lab if t.r_lab is not None else t.r_lab_ex for t in fts], dtype=float)
    out.update(G=float(g.mean()), Phi=float(phi.mean()), R_lab=float(lab.mean()),
               cost_lab_R=float((g - phi - lab).mean()), kstar=sweep.break_even_bp(g - phi, h))
    ones = np.ones(len(fts))
    _cis(out, "G", fts, g, ones)
    _cis(out, "Rlab", fts, lab, ones)
    _cis(out, "kstar", fts, g - phi, h, scale=2.0 / sweep.BP)
    sc = _sc_cluster(fts)
    out["ci_ok"] = sc is not None
    if sc:
        groups = [t.day for t in fts] if sc == "day" else [t.symbol for t in fts]
        out["sc_cluster"] = sc
        out["Rlab_sc"] = sweep.ratio_ci(lab, ones, groups)
        for name, fee, slip, wf in SCENARIOS:
            if wf:
                r = np.array([t.scenario_r(fee_bp=fee, slip_bp=slip, with_funding=True) for t in fts], dtype=float)
                out[f"sc_{name}"] = sweep.ratio_ci(r, ones, groups)
    return out


def _ci(s: dict[str, object], name: str, nd: int) -> str:
    v = s.get(name)
    return "[—]" if v is None else f"[{v[1]:+.{nd}f}; {v[2]:+.{nd}f}]"  # type: ignore[index]


def table_main(rows: list[dict[str, object]]) -> None:
    print("key | TODOS: n/dias/merc · G bruto [IC dia] [IC merc] · k*_ex bp | COM FUNDING: n/dias/merc · R_lab · "
          "custo_Lab_R · Φ · G pareado · k* bp [IC dia] [IC merc] | dur p50 (p10–p90) min | trades/dia ativo")
    print("(spot: r_multiple é nulo; R_lab = R líquido reconstruído sem funding. [—] = piso de dias/mercados/n não atingido)")
    for s in rows:
        left = (f"{s['key']} | {s['n']}/{s['days']}/{s['markets']} · {s['G_all']:+.3f} {_ci(s, 'Gall_day', 3)} "
                f"{_ci(s, 'Gall_mkt', 3)} · {s['kstar_ex_all']:+.1f}")
        if "G" not in s:
            mid = " | sem funding estabelecido"
        else:
            mid = (f" | {s['n_f']}/{s['days_f']}/{s['mk_f']} · {s['R_lab']:+.3f} · {s['cost_lab_R']:.3f} · "
                   f"{s['Phi']:+.4f} · {s['G']:+.3f} {_ci(s, 'G_day', 3)} {_ci(s, 'G_mkt', 3)} · "
                   f"{s['kstar']:+.1f} {_ci(s, 'kstar_day', 1)} {_ci(s, 'kstar_mkt', 1)}")
        tail = (f" | {s['dur_p50']:.0f} ({s['dur_p10']:.0f}–{s['dur_p90']:.0f}) | {s['per_active_day']:.1f}")
        print(left + mid + tail)


def table_scenarios(rows: list[dict[str, object]]) -> None:
    names = [n for n, _, _, wf in SCENARIOS if wf]
    print("COM FUNDING (n com funding): key | n | IC por | R_lab [IC] | " + " | ".join(names)
          + " || TODOS (n todos, sem funding): spot_taker_10 [IC]   — R médio por trade em R do Lab [IC 95 %]")
    for s in rows:
        spot = s.get("sc_spot_taker_10")
        if not s.get("ci_ok") and spot is None:
            continue
        spot_txt = "—" if spot is None else f"{fmt_ci(*spot)} (n {s['n']}, IC por {s['sc_all_cluster']})"  # type: ignore[misc]
        if s.get("ci_ok"):
            cells = [fmt_ci(*s[f"sc_{n}"]) for n in names]  # type: ignore[misc]
            print(f"{s['key']} | {s['n_f']} | {s['sc_cluster']} | {fmt_ci(*s['Rlab_sc'])} | "  # type: ignore[misc]
                  + " | ".join(cells) + f" || {spot_txt}")
        else:  # o subconjunto com funding não tem IC, mas o cenário sem funding usa todos (Astra, rodada 2)
            print(f"{s['key']} | {s['n_f']} | — | sem IC no subconjunto com funding | "
                  + " | ".join("—" for _ in names) + f" || {spot_txt}")
    rt = {n: 2 * (fee + slip) for n, fee, slip, _ in SCENARIOS}
    print("\nida-e-volta de cada cenário (bp): Lab 20.0 · " + " · ".join(f"{n} {v:.1f}" for n, v in rt.items()))
    print("margem = k* − ida-e-volta do cenário (bp; >0 = sobra; o funding já está dentro de k*; população com funding):")
    for s in rows:
        if s.get("ci_ok"):
            k = float(s["kstar"])  # type: ignore[arg-type]
            print(f"  {s['key']}: k* {k:+.1f} → " + " · ".join(f"{n} {k - v:+.1f}" for n, v in rt.items()
                                                             if not n.startswith("spot")))


def table_months(groups: dict[tuple[str, ...], list[sweep.Trade]]) -> None:
    print("key | mês | n | dias | G bruto | R_lab | k* bp")
    for key, ts in groups.items():
        fts = funded(ts)
        if len(fts) < MIN_N:
            continue
        by_m: dict[str, list[sweep.Trade]] = defaultdict(list)
        for t in fts:
            by_m[t.month].append(t)
        for m in sorted(by_m):
            mt = by_m[m]
            g = np.array([t.gross_r for t in mt])
            phi = np.array([t.funding_r for t in mt], dtype=float)
            h = np.array([t.notional_per_r for t in mt])
            lab = np.array([t.r_lab if t.r_lab is not None else t.r_lab_ex for t in mt], dtype=float)
            print(f"{'/'.join(key)} | {m} | {len(mt)} | {len({t.day for t in mt})} | {g.mean():+.3f} | "
                  f"{lab.mean():+.3f} | {sweep.break_even_bp(g - phi, h):+.1f}")


def spot_desk() -> None:
    with open(HERE / "cache" / "spot.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    r = np.array([float(x["r_multiple"]) for x in rows])
    pnl = sum(float(x["pnl_sol"]) for x in rows)
    vs = sorted({f"{x['strategy']} {x['version']}" for x in rows})
    print(f"spot/1 (dinheiro real, Jupiter): {len(rows)} posições fechadas, {vs}, R gravado médio {r.mean():+.3f}, "
          f"Σ R {r.sum():+.3f}, Σ pnl_sol gravado {pnl:+.6f} (comparar com o 'real' da KB-0171, Σ −0,003938 SOL / "
          f"−4,40 R, já sem o erro do aluguel)")


def overlap(groups: dict[tuple[str, ...], list[sweep.Trade]]) -> None:
    """Fração de entradas (mercado, minuto de entrada) compartilhadas entre versões prospectivas da mesma estratégia."""
    big = {k: {(t.symbol, t.entry_ts) for t in ts} for k, ts in groups.items() if k[3] == "prosp" and len(ts) >= 100}
    keys = sorted(big)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if a[0] != b[0] or a[2] != b[2]:
                continue
            inter = len(big[a] & big[b])
            print(f"{a[0]} {a[1]}×{b[1]} ({a[2]}): comum {inter} · {inter / len(big[a]):.0%} de {a[1]} · "
                  f"{inter / len(big[b]):.0%} de {b[1]}")


def main() -> None:
    trades = load()
    groups: dict[tuple[str, ...], list[sweep.Trade]] = defaultdict(list)
    for t in trades:
        groups[group_key(t)].append(t)
    keys = sorted(groups, key=lambda k: (k[3] != "prosp", k[0], int(k[1][1:]), k[2], k[3]))
    print(f"lab-cost-sweep — {len(trades)} desfechos terminais (long, binance), {len(groups)} grupos; "
          f"bootstrap de clusters {sweep.REPS} réplicas, semente {sweep.SEED}, IC percentil 95 %\n")
    rows = [summary(k, groups[k]) for k in keys]
    for title, sel in (("PROSPECTIVO", lambda s: "/prosp" in str(s["key"])),
                       ("REPLAY (histórico reprocessado; não é coorte prospectiva)",
                        lambda s: "/replay:" in str(s["key"]))):
        sub = [s for s in rows if sel(s)]
        print(f"=== 1. {title} — R bruto, R do Lab, custo de equilíbrio ===")
        table_main(sub)
        print(f"\n=== 2. {title} — cenários de custo (funding como gravado; spot sem funding) ===")
        table_scenarios(sub)
        print()
    print("=== 3. Por mês (grupos com n ≥ 20 com funding) ===")
    table_months({k: groups[k] for k in keys})
    print("\n=== 4. Mesa spot/1 ===")
    spot_desk()
    print("\n=== 5. Sobreposição entre versões prospectivas (n ≥ 100): as linhas da tabela 1 NÃO são independentes ===")
    overlap({k: groups[k] for k in keys})


if __name__ == "__main__":
    main()
