"""Reads a density capture (``2026-10-06-wallet-tape-density-probe.py``) and prints the tables of the
"Densidade real" section of ``obsidian/06-DECISIONS/Dialogos/wallets-cpu.md``. Files only.

- **density** — per key (curve mint or PumpSwap pool) its busiest 60 min (exact sliding window):
  histogram, curve vs pool, top keys and their share, keys ≥ 1 000 / ≥ 4 000 events in an hour,
  and the event-weighted density Σn²/Σn (NOT a copy's: copies come from eligible bets);
- **cost multiplier (SCENARIO)** — each key's hour priced on the measured one-mint curve of
  ``hot-mint-sweep-2026-10-06-step3.txt`` (SYNTHETIC generator): linear below 1 000 events/h,
  log-log between the measured points, and beyond 16 000/h extended with an exponent given by
  ``--beyond`` (default: the sweep's last local exponents of quotes and of CPU, as a range).
  M = Σ C(n) / Σ C_linear(n) says how much more a night costs than if every event were priced at
  the 1 000/h rate. It inherits the generator's copies per mint, so it can err either way: low
  if a hot pool has many distinct buyers, high if it is a robot loop with few eligible bets.

    uv run --no-sync python infra/scripts/research/2026-10-06-wallet-tape-density-read.py \\
        --run .claude/state/carteiras-lucro/density/run1 \\
        --sweep .claude/state/carteiras-lucro/bench/hot-mint-sweep-2026-10-06-step3.txt
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

_BINS = ((1, 9), (10, 99), (100, 999), (1_000, 3_999), (4_000, 15_999), (16_000, 10**12))


def sweep_points(path: Path) -> list[tuple[int, float, int]]:
    rows = [json.loads(line[4:]) for line in path.read_text(encoding="utf-8").splitlines()
            if line.startswith("ROW ")]  # fmt: skip
    return sorted((int(r["events"]), float(r["cpu_s"]), int(r["stop_quotes"])) for r in rows)


def cost(n: int, pts: list[tuple[int, float, int]], beyond: float) -> float:
    """CPU seconds (sweep machine) of one key-hour with ``n`` events."""
    n0, c0, _ = pts[0]
    if n <= n0:
        return c0 * n / n0
    for (a, ca, _), (b, cb, _) in zip(pts, pts[1:], strict=False):
        if n <= b:
            k = math.log(cb / ca) / math.log(b / a)
            return ca * (n / a) ** k
    nl, cl, _ = pts[-1]
    return cl * (n / nl) ** beyond


def bin_of(n: int) -> str:
    lo, hi = next((lo, hi) for lo, hi in _BINS if lo <= n <= hi)
    return f"{lo:,}–{hi:,}" if hi < 10**12 else f"≥ {lo:,}"


def table(header: list[str], body: list[list[Any]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return "\n".join(out + ["| " + " | ".join(str(c) for c in row) + " |" for row in body])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--sweep", required=True)
    ap.add_argument("--beyond", default="", help="exponents past the sweep, e.g. '1.51,1.69'")
    args = ap.parse_args()
    reconfigure = getattr(sys.stdout, "reconfigure", None)  # Windows consoles default to cp1252
    if callable(reconfigure):
        reconfigure(encoding="utf-8")
    run = Path(args.run)
    d = json.loads((run / "density.json").read_text(encoding="utf-8"))
    summ = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    hours: dict[str, int] = d["busiest_60min_per_key"]
    if not hours:
        raise SystemExit(f"no sliding hour: {d['keys_over_1000_in_a_rolling_60min']}")
    rc = summ["snapshot"]["reconnects"]
    print(f"captura: {d['elapsed_s']:.1f} s de recepção (pedido {d['requested_s']:.0f} s), parada: "
          f"{d['stop_reason']}; recusas {len(d['refusals'])}; suspensões {len(d['suspensions'])}; "
          f"desconexões pump/amm {rc['pump']['disconnects']}/{rc['amm']['disconnects']}, downtime "
          f"{rc['pump']['downtime_s_incl_open']:.0f}/{rc['amm']['downtime_s_incl_open']:.0f} s")  # fmt: skip
    print(f"chaves {d['keys']:,}; swaps com chave {d['keyed_swap_events']:,} "
          f"({d['keyed_swap_events'] / d['elapsed_s']:.0f}/s); sem chave {d['unkeyed_swap_events']}; "
          f"pool inferida {d['inferred_keyed_swap_events']:,}")  # fmt: skip
    groups = {"curva": [n for k, n in hours.items() if k.startswith("curve:")],
              "pool": [n for k, n in hours.items() if k.startswith("pool:")]}  # fmt: skip
    groups["tudo"] = groups["curva"] + groups["pool"]
    print("\n## Hora mais cheia de cada chave (janela deslizante exata de 60 min)\n")
    body: list[list[Any]] = []
    for lo, hi in _BINS:
        row: list[Any] = [bin_of(lo)]
        for g in ("curva", "pool", "tudo"):
            sel = [n for n in groups[g] if lo <= n <= hi]
            tot = sum(groups[g]) or 1
            row += [f"{len(sel):,}", f"{100 * sum(sel) / tot:.1f} %"]
        body.append(row)
    print(table(["eventos na hora", "curva: chaves", "curva: eventos", "pool: chaves",
                 "pool: eventos", "tudo: chaves", "tudo: eventos"], body))  # fmt: skip
    print("\n## Resumo por programa\n")
    body = []
    for g in ("curva", "pool", "tudo"):
        ns = sorted(groups[g], reverse=True)
        tot = sum(ns) or 1
        dstar = sum(n * n for n in ns) / tot
        body.append([g, f"{len(ns):,}", f"{sum(ns):,}", f"{ns[0]:,}" if ns else "—",
                     f"{100 * ns[0] / tot:.1f} %" if ns else "—", f"{100 * sum(ns[:10]) / tot:.1f} %",
                     sum(1 for n in ns if n >= 1_000), sum(1 for n in ns if n >= 4_000),
                     f"{ns[len(ns) // 2]:,}" if ns else "—", f"{dstar:,.0f}"])  # fmt: skip
    print(table(["programa", "chaves", "Σ hora mais cheia", "maior chave", "fatia da maior",
                 "fatia das 10 maiores", "≥ 1 000/h", "≥ 4 000/h", "mediana", "Σn²/Σn"], body))  # fmt: skip
    print("\n## As 10 chaves mais cheias\n")
    top = sorted(hours.items(), key=lambda kv: -kv[1])[:10]
    allh = sum(hours.values())
    print(table(["programa", "chave", "eventos na hora", "fatia", "máx. por minuto"],
                [[k.split(":")[0], k.split(":")[1][:10] + "…", f"{n:,}", f"{100 * n / allh:.1f} %",
                  max(d["per_key_minutes"][k].values())] for k, n in top]))  # fmt: skip
    pts = sweep_points(Path(args.sweep))
    lin = pts[0][1] / pts[0][0]
    ks = [math.log(pts[-1][1] / pts[-2][1]) / math.log(pts[-1][0] / pts[-2][0]),
          math.log(pts[-1][2] / pts[-2][2]) / math.log(pts[-1][0] / pts[-2][0])]  # fmt: skip
    beyond = [float(x) for x in args.beyond.split(",")] if args.beyond else sorted(ks)
    print("\n## Multiplicador de custo pela densidade (CENÁRIO, curva sintética do mint quente)\n")
    body = []
    for b in beyond:
        for g in ("curva", "pool", "tudo"):
            c = sum(cost(n, pts, b) for n in groups[g])
            base = lin * sum(groups[g]) or 1e-9
            hot = cost(max(groups[g]), pts, b) if groups[g] else 0.0
            body.append([f"{b:.2f}", g, f"{c:,.1f} s", f"{base:,.1f} s", f"{c / base:.2f}×",
                         f"{hot:,.1f} s"])  # fmt: skip
    print(table(["expoente além de 16 000/h", "programa", "custo da hora (Σ C(n))",
                 "linear a 1 000/h", "M", "maior chave sozinha"], body))  # fmt: skip


if __name__ == "__main__":
    main()
