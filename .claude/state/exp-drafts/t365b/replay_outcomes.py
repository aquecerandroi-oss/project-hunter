"""T3.65b -- re-resolve os DESFECHOS REAIS dos tres mercados de 4 h com o codigo
de HOJE, sobre as linhas de `funding_rates` de hoje, e compara com o que esta
gravado em `signal_outcomes`.

Nao e a recomputacao (`infra/scripts/recompute_funding.py`): nada e escrito. E a
resposta a "como `resolve_funding`/`_cadence` classificaria cada janela de
desfecho ao redor da transicao", com as janelas REAIS, nao hipoteticas.

Limite declarado: `ambiguous_from` (a barra de saida de um toque intrabar) nao
esta no CSV, entao aqui todo desfecho e resolvido como se a saida fosse exata --
o guarda `funding_ambiguous_exit` nao pode ser reproduzido e aparece como
divergencia esperada.
"""

from __future__ import annotations

import csv
import pathlib
import sys
from bisect import bisect_left, bisect_right
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4] / "services/strategy-worker"))

from hunter_strategy_worker.funding import (  # noqa: E402
    MATCH_TOLERANCE,
    Settlement,
    resolve_funding,
)

HERE = pathlib.Path(__file__).resolve().parent
LOOKBACK = timedelta(days=3)


def parse(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=UTC)


def main() -> int:
    rows: dict[str, list[Settlement]] = {}
    with (HERE / "funding-real.csv").open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rows.setdefault(row["symbol"], []).append(
                Settlement(parse(row["t"]), Decimal(row["rate"]), Decimal(row["mark_price"]))
            )
    tally: Counter[str] = Counter()
    changed: list[str] = []
    with (HERE / "outcomes-real.csv").open(newline="", encoding="utf-8") as fh:
        for out in csv.DictReader(fh):
            symbol = out["symbol"]
            series = rows[symbol]
            times = [s.funding_time for s in series]
            entry, exit_ = parse(out["entry_ts"]), parse(out["exit_ts"])
            lo = bisect_left(times, entry - LOOKBACK)
            hi = bisect_right(times, exit_ + MATCH_TOLERANCE)
            reading = resolve_funding(series[lo:hi], entry_ts=entry, exit_ts=exit_)
            gravado = out["motivo"] or None
            agora = reading.reason
            key = f"{gravado or 'ok'} -> {(agora or 'ok').split(':')[0]}"
            tally[key] += 1
            if (gravado or "").split(":")[0] != (agora or "").split(":")[0]:
                changed.append(
                    f"{symbol} {out['cohort'][:18]:18} {entry:%m-%d %H:%M}->{exit_:%m-%d %H:%M} "
                    f"gravado={gravado} agora={agora} interval_s={reading.interval_s}"
                )
    print(f"desfechos re-resolvidos: {sum(tally.values())}")
    for key, n in sorted(tally.items(), key=lambda kv: -kv[1]):
        print(f"  {key}: {n}")
    print(f"\nmudariam de veredito: {len(changed)}")
    for line in changed:
        print("  " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
