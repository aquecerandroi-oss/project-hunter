"""T3.65b -- roda o resolver REAL (`hunter_strategy_worker.funding.resolve_funding`)
sobre as LINHAS REAIS de `funding_rates` de PROM/SAHARA/TAO nos 90 dias.

Nao reimplementa o resolver: importa-o. O que este script constroi e a VERDADE
CONHECIDA contra a qual comparar -- a grade real de cada mercado, lida do
histograma de gaps da q00/q01 e das eras que ele revela:

  PROM   4 h ate 2026-08-11 04:00Z; 1 h de 05:00Z ate 2026-08-14 10:00Z;
         4 h de novo a partir de 2026-08-14 12:00Z -- o ultimo assentamento de
         1 h foi 10:00Z e o seguinte foi 12:00Z (a volta cai no proximo ponto
         da grade de 4 h depois do 17.o ciclo, coerente com a regra Binance de
         02/01/2026 -- 16 ciclos <= 0,025 %);
  SAHARA/TAO   4 h o tempo todo.
  Os tres perdem o assentamento de 2026-06-24 04:00Z -- lacuna de COLETA (o
  MESMO instante nos tres mercados), nao mudanca de cadencia.

Para cada janela hipotetica (entry, exit] -- entradas de 15 em 15 min, sete
duracoes de 15 min a 12 h, a mesma janela de historico de `settle()`
([entry - 3 d, exit + 2 s]) -- o veredito ESPERADO e:
  * `funding_missing` se algum instante da grade real dentro da janela nao tem
    linha no nosso banco (a lacuna de coleta) -- e a resposta honesta;
  * senao, cobranca igual a soma de rate*mark das linhas reais em (entry, exit].

As recusas indevidas sao separadas em duas familias, porque tem causas
diferentes e so uma delas e a que a Astra previu:
  * `falso_missing_borda` -- o instante nominal reclamado esta a menos de
    MATCH_TOLERANCE de uma linha REAL que caiu FORA da janela (tipicamente o
    assentamento carimbado alguns ms DEPOIS de uma saida em minuto redondo).
    O evento existe e nao foi pago; chamar de ausente e errado.
  * `falso_missing_grade` -- nao ha linha real perto do instante nominal: a
    grade inferida nao e a grade real (transicao de cadencia).

SOMENTE LEITURA de um CSV exportado da VPS. Nenhuma escrita.
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
CSV_PATH = HERE / "funding-real.csv"
LOOKBACK = timedelta(days=3)
HOLDINGS = [
    timedelta(minutes=15),
    timedelta(minutes=30),
    timedelta(hours=1),
    timedelta(hours=2),
    timedelta(hours=4),
    timedelta(hours=8),
    timedelta(hours=12),
]

ERAS: dict[str, list[tuple[datetime, int]]] = {
    "PROMUSDT": [
        (datetime(2026, 6, 1, tzinfo=UTC), 14400),
        (datetime(2026, 8, 11, 5, tzinfo=UTC), 3600),
        (datetime(2026, 8, 14, 11, tzinfo=UTC), 14400),
    ],
    "SAHARAUSDT": [(datetime(2026, 6, 1, tzinfo=UTC), 14400)],
    "TAOUSDT": [(datetime(2026, 6, 1, tzinfo=UTC), 14400)],
}
END = datetime(2026, 9, 11, tzinfo=UTC)


def load() -> dict[str, list[Settlement]]:
    out: dict[str, list[Settlement]] = {}
    with CSV_PATH.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ts = datetime.strptime(row["t"], "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=UTC)
            out.setdefault(row["symbol"], []).append(
                Settlement(ts, Decimal(row["rate"]), Decimal(row["mark_price"]))
            )
    return out


def true_grid(symbol: str, start: datetime, end: datetime) -> list[datetime]:
    """Os instantes em que a exchange REALMENTE assentou, em (start, end]."""
    eras = ERAS[symbol]
    out: list[datetime] = []
    for i, (era_start, interval) in enumerate(eras):
        era_end = eras[i + 1][0] if i + 1 < len(eras) else END
        step = timedelta(seconds=interval)
        cursor = datetime(2026, 6, 1, tzinfo=UTC)
        if cursor < max(era_start, start):
            jumps = int((max(era_start, start) - cursor) / step)
            cursor += jumps * step
        while cursor <= min(era_end - timedelta(seconds=1), end):
            if cursor > start:
                out.append(cursor)
            cursor += step
    return out


def main() -> int:
    data = load()
    tally: Counter[str] = Counter()
    examples: dict[str, list[str]] = {}
    for symbol, rows in sorted(data.items()):
        times = [r.funding_time for r in rows]
        minutes = {t.replace(second=0, microsecond=0) for t in times}
        entry = times[0] + LOOKBACK
        last = times[-1]
        while entry < last:
            for hold in HOLDINGS:
                exit_ = entry + hold
                if exit_ > last:
                    continue
                lo = bisect_left(times, entry - LOOKBACK)
                hi = bisect_right(times, exit_ + MATCH_TOLERANCE)
                history = rows[lo:hi]
                reading = resolve_funding(history, entry_ts=entry, exit_ts=exit_)
                grid = true_grid(symbol, entry, exit_)
                holes = [g for g in grid if g.replace(second=0, microsecond=0) not in minutes]
                inside = rows[bisect_right(times, entry) : bisect_right(times, exit_)]
                expected = sum((r.rate * r.mark_price for r in inside), Decimal(0))
                reason = reading.reason
                # A grade-verdade so e conhecida ao MINUTO: o instante real de um
                # assentamento que NAO temos (a lacuna de 24/06) carrega ms que
                # ninguem pode reconstruir, e uma janela cuja borda cai a menos de
                # 2 s de um ponto da grade nao tem veredito determinado por este
                # script. Elas sao contadas a parte, nunca como defeito.
                # So o BURACO e indeterminado: de um assentamento que temos, o
                # carimbo real e conhecido ao ms e nao ha duvida nenhuma.
                edge_grid = true_grid(
                    symbol, entry - MATCH_TOLERANCE - timedelta(seconds=1), exit_ + MATCH_TOLERANCE
                )
                near_edge = any(
                    (abs(h - entry) <= MATCH_TOLERANCE or abs(h - exit_) <= MATCH_TOLERANCE)
                    and h.replace(second=0, microsecond=0) not in minutes
                    for h in edge_grid
                )
                if near_edge:
                    key = "indeterminado_ms"
                elif holes:
                    key = (
                        "lacuna_de_coleta_detectada"
                        if reason and reason.startswith("funding_missing")
                        else f"lacuna_de_coleta_NAO_detectada({reason})"
                    )
                elif reason is None:
                    key = "cobrado_certo" if reading.per_unit == expected else "cobrado_ERRADO"
                elif reason.startswith("funding_missing:"):
                    claimed = datetime.fromisoformat(reason.split(":", 1)[1])
                    j = bisect_left(times, claimed - MATCH_TOLERANCE)
                    near = [t for t in times[j : j + 4] if abs(t - claimed) <= MATCH_TOLERANCE]
                    if not near:
                        key = "falso_missing_grade"
                    elif all(t > exit_ for t in near):
                        key = "falso_missing_borda_saida"
                    elif all(t <= entry for t in near):
                        key = "falso_missing_borda_entrada"
                    else:
                        key = "falso_missing_borda_dentro"
                else:
                    key = f"recusado:{reason.split(':')[0]}"
                tally[f"{symbol}|{key}"] += 1
                if not key.startswith(("cobrado_certo", "lacuna_de_coleta_detectada")):
                    examples.setdefault(f"{symbol}|{key}", []).append(
                        f"{entry:%Y-%m-%d %H:%M} -> {exit_:%Y-%m-%d %H:%M} "
                        f"interval_s={reading.interval_s} reason={reason} esperado={expected}"
                    )
            entry += timedelta(minutes=15)
    print(f"janelas avaliadas: {sum(tally.values())}")
    for key, n in sorted(tally.items()):
        print(f"  {key}: {n}")
    print()
    for key, lines in sorted(examples.items()):
        print(f"--- {key} ({len(lines)}), primeiros 3 e ultimos 2:")
        for line in lines[:3] + (["   ..."] if len(lines) > 5 else []) + lines[-2:]:
            print("   " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
