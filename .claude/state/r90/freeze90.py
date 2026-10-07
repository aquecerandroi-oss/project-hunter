"""R90 — monta as linhas causais (folga 15/30/60, guarda da janela pelo outbox) e congela a lista elegível ANTES de
ler qualquer desfecho. Só usa a NULIDADE de R_net.

cd .claude/state/r90 && PYTHONPATH=C:/dev/project-hunter uv run --no-sync --project C:/dev/project-hunter python freeze90.py
"""

from __future__ import annotations

import csv
import hashlib
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

from data90 import CACHE, STRATS, WINDOW, load_ev, load_rows, ts, window_evidence

FULL = ("x", "d_low", "ret4h", "atr_pct")


RAW_OI = CACHE.parent / "replica" / "cache" / "oi_raw.csv"  # SELECT cru (cego) dos mercados da momentum elegível


def used_buckets() -> dict[str, list[datetime]]:
    """Buckets com OI > 0 por mercado, do export cru — para certificar a janela que a mediana usou."""
    out: dict[str, list[datetime]] = defaultdict(list)
    if RAW_OI.exists():
        with RAW_OI.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                t = ts(r["ts"])
                if t is not None and float(r["open_interest"]) > 0:
                    out[r["market_id"]].append(t)
    return out


def build(lag: int) -> list[dict]:
    """Linhas da folga `lag` com a guarda da janela inteira pelo outbox (amostra inserida depois de obs = recusa)."""
    rows = load_rows(CACHE / f"feat2_{lag}.csv", timedelta(minutes=lag))
    ev, start = load_ev()
    raw = used_buckets()
    for r in rows:
        r["window_proven"] = False
        if r["why"] is None:
            used = ({b for b in raw[r["market"]] if r["oi_ts"] - WINDOW < b <= r["oi_ts"]}
                    if r["market"] in raw else None)
            late, proven = window_evidence(ev.get(r["symbol"], {}), r["oi_ts"], r["obs"], start, used)
            if late:
                r["why"], r["x"] = "oi_janela_chegou_depois", None
            r["window_proven"] = proven
    return rows


def complete(r: dict) -> bool:
    return bool(r["has_r"]) and r["why"] is None and all(r[v] is not None for v in FULL)


def main() -> None:
    rows = build(15)
    ids = [r["signal_id"] for r in rows]
    assert len(ids) == len(set(ids)), "signal_id repetido no export"
    print("motivos de fora (folga 15):", dict(Counter((r["strategy"], r["why"]) for r in rows if r["why"])))
    elig = sorted((r["signal_id"], r["strategy"]) for r in rows if complete(r))
    body = "signal_id,strategy\n" + "".join(f"{s},{k}\n" for s, k in elig)
    (CACHE / "eligible.csv").write_text(body, encoding="utf-8", newline="\n")
    print(f"congelado em {datetime.now(UTC).isoformat(timespec='seconds')}")
    print("elegíveis por estratégia:", dict(Counter(k for _, k in elig)), "| decidem:", STRATS)
    print("janela inteira provada pós-commit:", sum(r["window_proven"] for r in rows if complete(r)),
          "| leitura corrente provada:", sum(r["verified"] for r in rows if complete(r)),
          "| com velas tardias:", sum(r["late_candles"] for r in rows if complete(r)))
    for lag in (30, 60):
        e2 = {r["signal_id"] for r in build(lag) if complete(r)}
        print(f"folga {lag}: elegíveis {len(e2)} | interseção com 15: {len(e2 & {s for s, _ in elig})}")
    print("sha256 eligible.csv:", hashlib.sha256(body.encode()).hexdigest())


if __name__ == "__main__":
    main()
