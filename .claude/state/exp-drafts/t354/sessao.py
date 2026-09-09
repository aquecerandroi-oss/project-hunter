"""T3.54 entrega 4 — a "abertura" revisitada: expectativa por balde de hora do
dia (UTC e Brasilia) nas coortes de replay que existem hoje.

Le `decisoes.csv` (q11). Baldes de 4 h em UTC, mais as tres aberturas nomeadas
(00:00 UTC = virada do dia; 13:30 UTC = NY; 12:00 UTC = 09:00 BRT), cada uma
como a hora cheia que a contem.
"""

from __future__ import annotations

import csv
from collections import defaultdict

CSV = "C:/dev/project-hunter/.claude/state/exp-drafts/t354/decisoes.csv"
COHORTS = {
    "session_orb v1": "replay:3fb9dda2",
    "mean_reversion v10": "replay:71c76d86",
    "mean_reversion v6": "replay:9d99748b",
    "momentum v10": "replay:6eff77c0",
    "momentum v8": "replay:ee11d60b",
}


def main() -> None:
    rows: list[dict[str, str]] = []
    with open(CSV, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if COHORTS.get(row["versao"]) == row["coorte"]:
                rows.append(row)

    for versao in COHORTS:
        mine = [r for r in rows if r["versao"] == versao]
        if not mine:
            continue
        print(f"\n{versao}  ({COHORTS[versao]})  n={len(mine)}")
        buckets: dict[str, list[float]] = defaultdict(list)
        for r in mine:
            h = int(r["hora_utc"])
            buckets[f"{h // 4 * 4:02d}-{h // 4 * 4 + 3:02d} UTC"].append(float(r["r_net"]))
        print("  balde de 4 h (UTC / = BRT-3)      n   soma R    media R")
        for label in sorted(buckets):
            values = buckets[label]
            start = int(label[:2])
            brt = f"{(start - 3) % 24:02d}-{(start + 3 - 3) % 24:02d} BRT"
            print(
                f"  {label} / {brt:<12} {len(values):>3}  {sum(values):+7.2f}  "
                f"{sum(values) / len(values):+.4f}"
            )
        for name, hours in (
            ("virada do dia 00:00-00:59 UTC", {0}),
            ("abertura Europa 07:00-07:59 UTC", {7}),
            ("abertura BRT 12:00-12:59 UTC (09:00 BRT)", {12}),
            ("abertura NY 13:00-14:59 UTC", {13, 14}),
        ):
            values = [float(r["r_net"]) for r in mine if int(r["hora_utc"]) in hours]
            if values:
                print(
                    f"  {name}: n={len(values)} soma={sum(values):+.2f} R "
                    f"media={sum(values) / len(values):+.4f} R"
                )
            else:
                print(f"  {name}: n=0")


if __name__ == "__main__":
    main()
