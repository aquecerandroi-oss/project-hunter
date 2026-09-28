"""R85 — H-025/H-026 no painel real do R84.

    uv run python .claude/state/r85/run_real.py counts   # só contagens de eventos (nenhum retorno)
    uv run python .claude/state/r85/run_real.py full     # protocolo inteiro → h025_h026.txt

Nada de base, VPS ou rede: o dado é o artefato de pesquisa `r84/cache/candles_1d.csv`.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from analyze85 import report  # noqa: E402
from collect85 import D_FIRST, D_LAST, collect, lookahead_real  # noqa: E402
from config import AS_OF_DAY, day_iso, trading_symbols  # noqa: E402
from data85 import apply_links_hl, build_hl_panel, load_rows_hl  # noqa: E402


def main(mode: str) -> None:
    t0 = time.time()
    rows, trading = apply_links_hl(load_rows_hl(), set(trading_symbols()))
    hp = build_hl_panel(rows, trading)
    head = [f"# R85 — H-025/H-026 no dado real (as_of {day_iso(AS_OF_DAY)}; sinais {day_iso(D_FIRST)} → {day_iso(D_LAST)})",
            f"velas {len(rows)}; séries {len(hp.p.ids)}; painel carregado em {time.time() - t0:.0f} s"]
    if mode == "counts":
        col = collect(hp, counts_only=True)
        text = "\n".join([*head, "## CONTAGENS (sem retorno)", str(dict(sorted(col.counts.items())))])
        (HERE / "counts.txt").write_text(text + "\n", encoding="utf-8")
        print(text)
        return
    col = collect(hp)
    body, verdicts = report(col)
    rng = np.random.default_rng(20260928)
    sample = sorted(rng.choice(np.arange(D_FIRST, D_LAST + 1) - hp.p.day0, size=25, replace=False).tolist())
    bad = lookahead_real(rows, trading, hp, sample)
    tail = [f"\nantecipação no dado real: {len(sample)} dias de sinal reconstruídos só com velas de abertura ≤ d "
            f"(universo + bandeiras de todas as faixas, controles e tolerâncias); divergências: {bad if bad else 'nenhuma'}",
            f"VEREDITOS: {verdicts}", f"tempo total {time.time() - t0:.0f} s"]
    text = "\n".join([*head, body, *tail])
    (HERE / "h025_h026.txt").write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "counts")
