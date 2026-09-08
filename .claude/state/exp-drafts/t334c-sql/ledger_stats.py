"""T3.34c — o livro-razão do dia um, agregado. Puro NumPy/coleções, sem pandas.

Responde, na ordem de prioridade que o brief da T3.34c fixou:
  (a) a geometria existe no dado real? (`no_line` / linhas por barra avaliada)
  (b) contagem bruta de decisões (K1)
  (c) `risk_too_wide` e `geometry_invalidation` separados, sobre a base certa
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict

import numpy as np


def main(paths: list[str]) -> None:
    states: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    per_market_state: defaultdict[str, Counter[str]] = defaultdict(Counter)
    lines_hist: Counter[int] = Counter()
    pivots_no_line: list[int] = []
    rejected_by_reason: Counter[str] = Counter()
    rejected_rows: list[dict] = []
    rows = 0

    for path in paths:
        with open(path, encoding="utf-8") as handle:
            for raw in handle:
                row = json.loads(raw)
                rows += 1
                state, reason = row["state"], row.get("reason", "")
                detail = row.get("detail") or {}
                states[state] += 1
                reasons[reason] += 1
                per_market_state[row["market"]][state] += 1
                if reason == "no_line":
                    lines_hist[0] += 1
                    pivots_no_line.append(int(detail.get("pivots", 0)))
                elif "lines" in detail:
                    lines_hist[int(detail["lines"])] += 1
                if state == "rejected":
                    rejected_by_reason[reason] += 1
                    rejected_rows.append({**detail, "reason": reason, "market": row["market"]})

    print(f"linhas={rows}")
    print("estados:", dict(states.most_common()))
    print("motivos:", dict(reasons.most_common()))

    # (a) a geometria existe? -- base = barras que passaram do aquecimento
    evaluable = rows - states.get("unavailable", 0)
    with_geometry = sum(n for k, n in lines_hist.items() if k > 0)
    no_line = lines_hist.get(0, 0)
    # `no_line` e o unico estado que prova ZERO linhas: toda barra que passou dele
    # tinha >= 1 linha, mesmo quando o detalhe nao carrega a contagem.
    print(
        "\n(a) GEOMETRIA: "
        f"avaliaveis={evaluable} "
        f"com_linha={evaluable - no_line} ({100 * (evaluable - no_line) / evaluable:.2f} %) "
        f"no_line={no_line} ({100 * no_line / evaluable:.2f} %)"
    )
    print(
        f"    (histograma sobre {with_geometry + no_line} barras: as `no_line` e as "
        f"`no_event`, as unicas cujo detalhe traz a contagem de linhas)"
    )
    counted = sorted(lines_hist.items())
    print("    linhas validas por barra:", counted)
    if with_geometry:
        values = np.repeat(
            np.array([k for k, _ in counted], dtype=np.int64),
            np.array([n for _, n in counted], dtype=np.int64),
        )
        print(
            f"    media={values.mean():.4f} p50={np.percentile(values, 50):.1f} "
            f"p90={np.percentile(values, 90):.1f} max={values.max()}"
        )
    if pivots_no_line:
        pivots = np.array(pivots_no_line, dtype=np.int64)
        print(
            f"    pivos nas barras SEM linha: media={pivots.mean():.3f} "
            f"p50={np.percentile(pivots, 50):.1f} max={pivots.max()} zero={int((pivots == 0).sum())}"
        )

    # (c) as recusas de geometria, sobre a base "de outro modo teriam disparado"
    triggered = states.get("triggered", 0)
    rejected = states.get("rejected", 0)
    base = triggered + rejected
    print(f"\n(c) RECUSAS: triggered={triggered} rejected={rejected} base={base}")
    for reason, n in rejected_by_reason.most_common():
        print(f"    {reason:24s} {n:4d}  {100 * n / base:6.2f} % da base")

    print("\n    por mercado (estado):")
    for market in sorted(per_market_state):
        counts = per_market_state[market]
        print(f"    {market:20s} {dict(counts.most_common())}")

    if rejected_rows:
        print("\n    as recusas, uma a uma:")
        for row in rejected_rows:
            print(
                f"    {row['market']:20s} {row['reason']:22s} "
                f"ref={row.get('reference_price')} stop={row.get('stop')} "
                f"linha={str(row.get('line_price_at_decision'))[:12]} risk={row.get('risk')}"
            )


if __name__ == "__main__":
    main(sys.argv[1:])
