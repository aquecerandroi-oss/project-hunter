"""R84 — integridade: saltos abertura(t) ÷ fecho(t−1) em dias consecutivos (redenominação sob o mesmo ticker?) e
maiores retornos semanais moeda a moeda DENTRO do universo (erro de dado vira semana extrema). Saída: integrity.txt."""
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from analyze import mondays  # noqa: E402
from config import AS_OF_DAY, EXCLUDED, LAST_T_DAY, apply_links, day_iso, load_rows, trading_symbols  # noqa: E402
from engine import week  # noqa: E402
from gaps import KEEP_TOGETHER  # noqa: E402
from panel import build_panel  # noqa: E402

rows, trading = apply_links(load_rows(), set(trading_symbols()))
by = defaultdict(dict)
for s, d, o, c, v in rows:
    by[s][d] = (o, c)
jumps = []
for s, dd in by.items():
    ks = sorted(dd)
    for a, b in zip(ks, ks[1:]):
        if b == a + 1 and dd[a][1] > 0:
            x = dd[b][0] / dd[a][1]
            if x > 1.5 or x < 1 / 1.5:
                jumps.append((round(x, 4), s, day_iso(b)))
out = [f"saltos abertura/fecho anterior fora de [1/1,5; 1,5] em dias consecutivos: {len(jumps)}"]
out += [f"  {j}" for j in sorted(jumps, key=lambda j: -abs(np.log(j[0])))[:40]]
p = build_panel(rows, trading, EXCLUDED, AS_OF_DAY, keep_together=KEEP_TOGETHER)
ts = mondays(p, LAST_T_DAY)
cw = []
for t in ts:
    for i in week(p, t, 14).idx:
        r = p.open_ff[i, t + 7] / p.open_ff[i, t] - 1 if p.last[i] >= t + 7 else float("nan")
        cw.append((r, p.ids[i], day_iso(p.day0 + t)))
cw = [c for c in cw if np.isfinite(c[0])]
cw.sort()
out.append(f"moeda-semanas no universo: {len(cw)}; 10 piores e 10 melhores:")
out += [f"  {c[0]:+.3f} {c[1]} {c[2]}" for c in cw[:10] + cw[-10:]]
Path(__file__).with_name("integrity.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))
