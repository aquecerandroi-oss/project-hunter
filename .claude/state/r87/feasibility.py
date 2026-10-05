"""R87 passo 0b — viabilidade só com datas e volume à vista (sem retorno, sem funding, sem preço de perp).

Quais séries à vista do R84 chegam ao top-40 de volume em alguma segunda desde 2019-09-09, e qual o nome do perpétuo
candidato pela regra congelada (BASE+USDT, 1000BASE, 1000000BASE, 1MBASE).
"""

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
R84 = HERE.parent / "r84"
sys.path.insert(0, str(R84))
from config import AS_OF_DAY, EXCLUDED, apply_links, day_iso, load_rows, trading_symbols  # noqa: E402
from engine import VOL_WINDOW, listed  # noqa: E402
from gaps import KEEP_TOGETHER  # noqa: E402
from panel import build_panel  # noqa: E402

PREFIXES = (("", 1.0), ("1000", 1000.0), ("1000000", 1e6), ("1M", 1e6))


def main() -> None:
    raw = load_rows()
    rows, trading = apply_links(raw, set(trading_symbols()))
    p = build_panel(rows, trading, EXCLUDED, AS_OF_DAY, keep_together=KEEP_TOGETHER)
    um = set((HERE / "cache" / "um_klines_symbols.txt").read_text(encoding="utf-8").split())
    first_mon = p.day0 + ((4 - p.day0) % 7)
    start = 18148  # 2019-09-09 (época), 1.ª segunda depois do BTCUSDT perpétuo (2019-09-08)
    cols = [t for t in range(first_mon - p.day0, AS_OF_DAY - 14 - p.day0, 7) if p.day0 + t >= start]
    seen: dict[str, int] = {}
    for t in cols:
        cand = np.flatnonzero(listed(p, t))
        vol = np.nansum(p.qvol[cand, max(t - VOL_WINDOW, 0): t], axis=1)
        for k in np.argsort(-vol)[:40]:
            sym = p.ids[cand[k]].split("#")[0]
            seen[sym] = seen.get(sym, 0) + 1
    hit, miss = {}, []
    for sym in sorted(seen):
        base = sym[:-4]
        names = [pre + base + "USDT" for pre, _ in PREFIXES if pre + base + "USDT" in um]
        if names:
            hit[sym] = names
        else:
            miss.append(sym)
    print(f"segundas {day_iso(p.day0 + cols[0])} → {day_iso(p.day0 + cols[-1])}: {len(cols)}")
    print(f"séries à vista no top-40 em alguma segunda: {len(seen)}; com perpétuo candidato no arquivo: {len(hit)}")
    print("com mais de um candidato:", {k: v for k, v in hit.items() if len(v) > 1})
    print("sem perpétuo (semanas no top-40):", sorted(((s, seen[s]) for s in miss), key=lambda x: -x[1]))


if __name__ == "__main__":
    main()


def write_candidates() -> None:
    """Grava cache/perp_candidates.txt (nomes de perpétuo dos candidatos; nenhuma leitura de preço)."""
    raw = load_rows()
    rows, trading = apply_links(raw, set(trading_symbols()))
    del rows, trading
    um = set((HERE / "cache" / "um_klines_symbols.txt").read_text(encoding="utf-8").split())
    spot_syms = sorted({r[0] for r in raw})
    names = sorted({pre + s[:-4] + "USDT" for s in spot_syms for pre, _ in PREFIXES if pre + s[:-4] + "USDT" in um})
    (HERE / "cache" / "perp_candidates.txt").write_text("\n".join(names) + "\n", encoding="utf-8")
    print(f"candidatos (todo par à vista do painel com perpétuo de mesmo ativo no arquivo): {len(names)}")
