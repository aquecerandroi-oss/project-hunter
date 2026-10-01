"""R86 — congela a lista de sinais elegíveis ANTES de ler qualquer desfecho (emenda 03:02Z, item 1).

cd .claude/state/r86 && PYTHONPATH=C:/dev/project-hunter uv run --no-sync --project C:/dev/project-hunter python freeze86.py
Escreve cache/eligible.csv (signal_id, strategy) e imprime o sha256. Só usa a NULIDADE de R_net.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from datetime import UTC, datetime

from data86 import CACHE, feature_rows, guard_window, load_daily

VARS = ("razao", "d_low", "ret4h", "atr_pct")


def complete(r: dict) -> bool:
    return bool(r["has_r"]) and all(r[v] is not None for v in VARS)


def main() -> None:
    rows, _ = feature_rows(load_daily())
    kept, refused = guard_window(rows)
    elig = sorted((r["signal_id"], r["strategy"]) for r in kept if complete(r))
    body = "signal_id,strategy\n" + "".join(f"{s},{k}\n" for s, k in elig)
    path = CACHE / "eligible.csv"
    path.write_text(body, encoding="utf-8", newline="\n")
    print(f"congelado em {datetime.now(UTC).isoformat(timespec='seconds')} | guarda recusou {refused}")
    print("elegíveis por estratégia:", dict(Counter(k for _, k in elig)))
    print("sha256 eligible.csv:", hashlib.sha256(body.encode()).hexdigest())


if __name__ == "__main__":
    main()
