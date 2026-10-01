"""H-026 B coorte prospectiva — contagem CEGA no painel histórico do R85 (só bandeiras; nenhum retorno é lido) e
conferência de que `detect_day` reproduz o R85.

    uv run --no-sync python .claude/state/h026b-forward/blind_counts.py   → blind_counts.txt

(1) Por dia de sinal de 2019-02-24 a 2026-09-16 (a janela do R85): eventos e comparadores dos dois contrastes da
H-028 — R (B × controle LTA do R85) e P (B que também é rompimento simples × rompimento simples sem toque A nas 21 velas
reais, o gatilho comum pedido pela Astra) — e intervalos de 28 d com evento. Serve para o poder e a parada. (2) Em 12 dias sorteados (6 quaisquer + 6 com B),
`detect_day` com só as velas ≤ d dá o mesmo universo e as mesmas bandeiras que a varredura do painel inteiro do R85
(comparando o símbolo-base: o rótulo "SYM#0" só aparece quando uma lacuna POSTERIOR parte a série — como no
`lookahead_real` do R85).
"""

from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "r85"))
sys.path.insert(0, str(HERE.parent / "r84"))

from brk import plain_breakout  # noqa: E402
from collect85 import D_FIRST, D_LAST  # noqa: E402
from config import trading_symbols  # noqa: E402
from data85 import apply_links_hl, build_hl_panel, load_rows_hl, universe  # noqa: E402
from detect_daily import B_WINDOW, TOL, detect_day  # noqa: E402
from geom85 import lta_scan, wilder_atr  # noqa: E402
from guards import iso  # noqa: E402


def main() -> None:
    t0 = time.time()
    rows, trading = apply_links_hl(load_rows_hl(), set(trading_symbols()))
    hp = build_hl_panel(rows, trading)
    p = hp.p
    flags: dict[int, np.ndarray] = {}  # série → (5, D): B, A, brk, ctrl, a20 no calendário

    def fl(i: int) -> np.ndarray:
        if i not in flags:
            cols = np.flatnonzero(~np.isnan(p.close[i]))
            h, lo, c = hp.high[i, cols], hp.low[i, cols], p.close[i, cols]
            s = lta_scan(h, lo, c, wilder_atr(h, lo, c), tol=TOL)
            a20 = np.array([s.a_events[max(0, t - B_WINDOW) : t + 1].any() for t in range(cols.size)], dtype=bool)
            arr = np.zeros((5, p.close.shape[1]), dtype=bool)
            arr[:, cols] = np.vstack([s.b_events, s.a_events, plain_breakout(h, c), s.ctrl, a20])
            flags[i] = arr
        return flags[i]

    n: Counter = Counter()
    ncmp_pday, nctrl_bday, b_days = [], [], []
    ev_days: dict[str, list[int]] = {"P": [], "R": [], "PR": []}
    coins_p: Counter = Counter()
    mem = {}
    for d in range(D_FIRST - p.day0, D_LAST - p.day0 + 1):
        mem[d] = universe(p, d + 1)
        f = np.array([fl(int(i))[:, d] for i in mem[d]])
        b, brk, ctrl, a20 = f[:, 0], f[:, 2], f[:, 3], f[:, 4]
        e_p, cmp_p = b & brk, brk & ~a20
        n["days"] += 1
        n["B"] += int(b.sum())
        n["brk"] += int(brk.sum())
        n["B_brk"] += int(e_p.sum())
        n["cmp_P"] += int(cmp_p.sum())
        if b.any():
            b_days.append(d)
            nctrl_bday.append(int(ctrl.sum()))
        if ctrl.any() and b.any():
            n["R_ev"] += int(b.sum())
            ev_days["R"] += [d] * int(b.sum())
        if e_p.any():
            ncmp_pday.append(int(cmp_p.sum()))
            if cmp_p.any():
                n["P_ev"] += int(e_p.sum())
                ev_days["P"] += [d] * int(e_p.sum())
                coins_p.update(p.ids[int(i)].split("#")[0] for i in np.asarray(mem[d])[e_p])
                if ctrl.any():
                    n["PR_ev"] += int(e_p.sum())
                    ev_days["PR"] += [d] * int(e_p.sum())
    d0 = D_FIRST - p.day0
    span = D_LAST - D_FIRST + 1
    cover = {k: len({(x - d0) // 28 for x in v if (x - d0) // 28 < span // 28}) for k, v in ev_days.items()}
    years = span / 365.25
    out = [f"# contagem cega (sem retorno) — sinais {iso(D_FIRST)} → {iso(D_LAST)}; painel R84 {len(rows)} velas, "
           f"{len(p.ids)} séries; tol {TOL}",
           f"dias {n['days']} ({years:.2f} anos); B brutos {n['B']} em {len(b_days)} dias; rompimentos simples {n['brk']}; "
           f"B que também são rompimento simples (evento P): {n['B_brk']}; comparadores P (rompimento sem toque A nas 21 velas) {n['cmp_P']}",
           f"contraste R (B × controle LTA do dia): {n['R_ev']} eventos ({n['R_ev'] / years:.1f}/ano), "
           f"{cover['R']} de {span // 28} intervalos de 28 d com evento",
           f"contraste P (B∩rompimento × rompimento sem teste no dia): {n['P_ev']} eventos ({n['P_ev'] / years:.1f}/ano), "
           f"{cover['P']} intervalos; nos dias com evento P, comparadores média {np.mean(ncmp_pday):.2f}, "
           f"mediana {np.median(ncmp_pday):.0f}, dias com 0: {sum(x == 0 for x in ncmp_pday)} de {len(ncmp_pday)}",
           f"evento P que também tem controle R no dia: {n['PR_ev']}; maior moeda nos eventos P: "
           f"{coins_p.most_common(1)[0] if coins_p else '-'} de {sum(coins_p.values())}",
           f"controles LTA nos dias com B: média {np.mean(nctrl_bday):.2f}"]
    # (2) conferência de fidelidade
    rng = np.random.default_rng(20261001)
    pool = np.arange(D_FIRST - p.day0, D_LAST - p.day0 + 1)
    sample = sorted(set(rng.choice(pool, 6, replace=False).tolist()) | set(rng.choice(b_days, 6, replace=False).tolist()))
    known = {r[0][:-4] for r in rows}
    bad = []
    for d in sample:
        rec = detect_day(rows, p.day0 + d, trading, known, {})
        want = [(p.ids[int(i)].split("#")[0], *(bool(x) for x in fl(int(i))[:, d])) for i in mem[d]]
        got = [(m["symbol"], *(m["flags"][k] for k in ("B", "A", "brk", "ctrl_lta", "a20"))) for m in rec["universe"]]
        if want != got:
            bad.append(iso(p.day0 + d))
    out.append(f"fidelidade: {len(sample)} dias ({', '.join(iso(p.day0 + d) for d in sample)}) — detect_day só com velas ≤ d "
               f"× varredura do painel inteiro: divergências {bad or 'nenhuma'}")
    out.append(f"tempo {time.time() - t0:.0f} s")
    text = "\n".join(out)
    (HERE / "blind_counts.txt").write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
