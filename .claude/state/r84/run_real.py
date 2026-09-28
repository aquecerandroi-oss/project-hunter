"""R84 passo 4 — H-024 no dado real. Só roda depois de audit.txt fechado (notes §4).

Saída: h024.txt (relatório do protocolo + descritivos + teste de antecipação no dado real).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from analyze import mondays, report, run  # noqa: E402
from config import AS_OF_DAY, EXCLUDED, LAST_T_DAY, apply_links, day_iso, load_rows, trading_symbols  # noqa: E402
from engine import targets, week  # noqa: E402
from gaps import KEEP_TOGETHER  # noqa: E402
from panel import build_panel  # noqa: E402


def lookahead_real(rows, trading, ts_days: list[int], p_full) -> list[str]:
    """Para T sorteados: painel construído só com velas de abertura < T dá o MESMO universo, sinal e alvos."""
    bad = []
    for t_day in ts_days:
        p_cut = build_panel([r for r in rows if r[1] < t_day], trading, EXCLUDED, AS_OF_DAY, day0=p_full.day0,
                            day_end=p_full.day0 + p_full.open.shape[1] - 1, keep_together=KEEP_TOGETHER)
        t = t_day - p_full.day0
        for lb in (7, 14, 28):
            a, b = week(p_full, t, lb), week(p_cut, t, lb)
            ia = [p_full.ids[i].split("#")[0] for i in a.idx]
            ib = [p_cut.ids[i].split("#")[0] for i in b.idx]
            if ia != ib or not np.allclose(a.m, b.m):
                bad.append(f"{day_iso(t_day)} lb{lb}")
            for arm in ("ew", "ts", "cs"):
                ta = {p_full.ids[i].split("#")[0]: w for i, w in targets(a, arm).items()}
                tb = {p_cut.ids[i].split("#")[0]: w for i, w in targets(b, arm).items()}
                if ta != tb:
                    bad.append(f"{day_iso(t_day)} lb{lb} {arm}")
    return bad


def main() -> None:
    raw = load_rows()
    rows, trading = apply_links(raw, set(trading_symbols()))
    p = build_panel(rows, trading, EXCLUDED, AS_OF_DAY, keep_together=KEEP_TOGETHER)
    ts = mondays(p, LAST_T_DAY)
    res = run(p, ts)
    out = [f"# R84 — H-024 no dado real (as_of {day_iso(AS_OF_DAY)}, último T {day_iso(LAST_T_DAY)})",
           "## Principal (continuidades documentadas ligadas; lacunas longas classificadas — notes §4)", report(res)]
    # sensibilidade: regra automática pura de §1.3 (toda lacuna ≥ 14 d parte, nenhuma migração ligada)
    p_raw = build_panel(raw, set(trading_symbols()), EXCLUDED, AS_OF_DAY)
    res_raw = run(p_raw, mondays(p_raw, LAST_T_DAY))
    out += ["## Sensibilidade (não decide): sem ligações de migração e com toda lacuna ≥ 14 d partida", report(res_raw)]
    if "arms" in res:
        r, ev = res["_r"], res["_ev"][14]
        ts_arr = np.array(ts)[ev]
        btc = p.ids.index("BTCUSDT")
        r_btc = np.array([p.open_ff[btc, t + 7] / p.open_ff[btc, t] - 1 for t in ts_arr])
        for name, x in (("TS [opt]", r[("ts", 14, "opt")][ev]), ("TS [pes]", r[("ts", 14, "pes")][ev]),
                        ("EW [opt]", r[("ew", 14, "opt")][ev]), ("BTC comprado-e-segurado", r_btc), ("caixa", np.zeros(ev.sum()))):
            sd = np.std(x, ddof=1)
            eq = np.cumprod(1 + x)
            dd = float(np.min(eq / np.maximum.accumulate(eq)) - 1)
            sh = float(np.mean(x) / sd * np.sqrt(52)) if sd > 0 else float("nan")
            out.append(f"descritivo {name}: média {np.mean(x) * 100:+.3f} %/sem, Sharpe anual {sh:.2f}, DD máx {dd * 100:.1f} %")
        wks = res["_wks"][14]
        names = [p.ids[i] for w in wks for i in w.idx]
        import json

        cat = json.loads((HERE / "cache" / "all_assets.json").read_text(encoding="utf-8"))["data"]
        tagged = {a["assetCode"] for a in cat if "bStocks" in (a.get("tags") or [])}
        bstock = [n for n in names if n.split("#")[0][:-4] in tagged]
        out.append(f"moeda-semanas no universo: {len(names)}; símbolos distintos {len(set(names))}; bStocks: "
                   f"{len(bstock)} moeda-semanas {sorted(set(bstock))}")
        rng = np.random.default_rng(20260928)
        sample = sorted(rng.choice(ts, size=25, replace=False).tolist())
        bad = lookahead_real(rows, trading, [p.day0 + t for t in sample], p)
        out.append(f"antecipação no dado real: {len(sample)} semanas × 3 lookbacks × 3 braços reconstruídas só com velas "
                   f"< T; divergências: {bad if bad else 'nenhuma'}")
    text = "\n".join(out) + "\n"
    (HERE / "h024.txt").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
