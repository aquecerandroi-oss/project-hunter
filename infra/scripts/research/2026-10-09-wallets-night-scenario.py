"""The night's CPU on the real density, before and after the step-4 stop index (SCENARIO, 09/10/2026).

Same method as the "Densidade real" section of ``obsidian/06-DECISIONS/Dialogos/wallets-cpu.md``
(``2026-10-06-wallet-tape-density-read.py``), with the cost curves re-measured on 09/10:

- the density is REAL: each key's busiest 60 min of the 06/10 capture (``density.json``,
  KB-0187) — one hour, one day; summing every key's busiest hour overstates a single hour;
- the cost of one key-hour with ``n`` events is SYNTHETIC: the replay of one hot key on top of
  the base background (``2026-10-09-wallets-stop-sweep.py``), curve keys on a curve sweep and pool
  keys on a pool sweep; linear below the first point, log-log between points, and past the last
  point the last local exponent;
- night = 168 × the hour (a 7-day window, ≈ 213 M fills at 352/s), as in step 3; the critical
  path = 168 × the largest key's hour (a key never splits across workers).

    uv run python infra/scripts/research/2026-10-09-wallets-night-scenario.py \\
        --run .claude/state/carteiras-lucro/density/run1 \\
        --curve <curve sweep> --pool <pool sweep> [--label before]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

HOURS_PER_NIGHT = 168


def points(path: Path) -> list[tuple[int, float]]:
    rows = [json.loads(line[4:]) for line in path.read_text(encoding="utf-8").splitlines()
            if line.startswith("ROW ")]  # fmt: skip
    return sorted((int(r["events"]), float(r["cpu_s"])) for r in rows)


def cost(n: int, pts: list[tuple[int, float]]) -> float:
    """CPU seconds of one key-hour with ``n`` events, on the sweep's machine."""
    (n0, c0), (nl, cl) = pts[0], pts[-1]
    if n <= n0:
        return c0 * n / n0
    for (a, ca), (b, cb) in zip(pts, pts[1:], strict=False):
        if n <= b:
            return ca * (n / a) ** (math.log(cb / ca) / math.log(b / a))
    (a, ca) = pts[-2]
    return cl * (n / nl) ** (math.log(cl / ca) / math.log(nl / a))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--curve", required=True)
    ap.add_argument("--pool", required=True)
    ap.add_argument("--label", default="")
    args = ap.parse_args()
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")
    hours: dict[str, int] = json.loads((Path(args.run) / "density.json").read_text("utf-8"))[
        "busiest_60min_per_key"
    ]
    curve_pts, pool_pts = points(Path(args.curve)), points(Path(args.pool))
    priced = [(k, n, cost(n, curve_pts if k.startswith("curve:") else pool_pts))
              for k, n in hours.items()]  # fmt: skip
    hour = sum(c for _, _, c in priced)
    curve_s = sum(c for k, _, c in priced if k.startswith("curve:"))
    top_key, top_n, top_c = max(priced, key=lambda r: r[2])
    events = sum(n for _, n, _ in priced)
    print(f"{args.label} curve sweep {args.curve} | pool sweep {args.pool}")
    print(f"keys {len(priced):,}, events in their busiest hours {events:,}")
    print(f"hour of the program: {hour:,.1f} s CPU (curve keys {curve_s:,.1f} s, pool keys "
          f"{hour - curve_s:,.1f} s); {1e6 * hour / events:.1f} us per event")  # fmt: skip
    print(f"largest key: {top_key[:16]}… {top_n:,} events -> {top_c:,.1f} s/h")
    print(f"night (x{HOURS_PER_NIGHT}): serial {HOURS_PER_NIGHT * hour / 3600:,.2f} h; critical path "
          f"{HOURS_PER_NIGHT * top_c / 3600:,.2f} h")  # fmt: skip


if __name__ == "__main__":
    main()
