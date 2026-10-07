"""h036 — gera a consulta de desfechos de uma CONSULTA DO CALENDÁRIO (L1 2027-01-06, L2 2027-04-07, L3 2027-07-07, às
12:00Z). Recusa gerar antes da data da consulta: é a única porta para os desfechos da coorte H-036.

``--ensaio``: ensaio do pipeline sobre a coorte EXPOSTA (sinais da v14 de 2026-09-09 19:37:36Z a 2026-10-07 00:00Z,
todos terminais antes do corte de 06:07Z; nenhum desfecho novo) — sem valor de evidência.

uso: python3 gen_look.py L1 > q_look_L1.sql ; bash q.sh q_look_L1.sql > cache/look_L1.csv
"""

import sys
from datetime import UTC, datetime, timedelta

T0 = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
LOOKS = {"L1": datetime(2027, 1, 6, 12, 0, tzinfo=UTC), "L2": datetime(2027, 4, 7, 12, 0, tzinfo=UTC),
         "L3": datetime(2027, 7, 7, 12, 0, tzinfo=UTC)}


def window(arg: str, ensaio: bool, now: datetime) -> tuple[datetime, datetime, str]:
    if ensaio:
        return (datetime(2026, 9, 9, 19, 37, 36, tzinfo=UTC), datetime(2026, 10, 7, 0, 0, tzinfo=UTC),
                "AND (o.exit_ts <= '2026-10-07 06:07:00+00' OR o.tracking_state::text = 'no_entry')")
    look = LOOKS[arg]
    if now < look:
        raise SystemExit(f"{arg} é {look.isoformat()}; agora {now.isoformat()} — consulta fora do calendário recusada")
    return T0, look - timedelta(hours=6), ""


def main() -> None:
    ensaio = "--ensaio" in sys.argv
    arg = next((a for a in sys.argv[1:] if not a.startswith("--")), "")
    de, ate, extra = window(arg, ensaio, datetime.now(UTC))
    print(f"""-- h036 consulta {'ENSAIO (coorte exposta)' if ensaio else arg} [{de.isoformat()}, {ate.isoformat()}) — gen_look.py
BEGIN READ ONLY;
SET LOCAL statement_timeout='600s';
COPY (
WITH v AS (SELECT sv.id FROM strategy_versions sv JOIN strategies st ON st.id = sv.strategy_id
           WHERE st.key = 'mean_reversion' AND sv.version = 'v14')
SELECT a.id AS signal_id, a.emitted_at, coalesce(o.tracking_state::text, 'sem_linha') AS tracking_state,
       o.result::text AS result, o.entry_ts, (o.meta->'progress'->>'exit_bar_open') AS xbo,
       (o.meta->'progress'->>'exit_at_open') AS x_at_open, o.meta->'progress'->>'exit_bar_high' AS x_high,
       o.virtual_targets->>0 AS target1, o.meta->'progress'->>'entry' AS entry_c,
       o.meta->'progress'->>'exit_base' AS exit_base, o.virtual_stop AS stop, m.symbol,
       o.meta->'funding'->>'per_unit' AS funding_per_unit, o.meta->'assumed_costs'->>'spread_bps' AS spread_bps,
       o.meta->'assumed_costs'->>'slippage_bps' AS slippage_bps
FROM agent_signals a JOIN v ON v.id = a.strategy_version_id JOIN markets m ON m.id = a.market_id
JOIN exchanges e ON e.id = m.exchange_id LEFT JOIN signal_outcomes o ON o.signal_id = a.id
WHERE a.emitted_at >= '{de.isoformat()}' AND a.emitted_at < '{ate.isoformat()}' AND a.direction::text = 'long'
  AND m.market_type::text = 'perpetual' AND e.code::text = 'binance'
  AND a.supporting_features->>'cohort' = 'prospective' {extra}
ORDER BY a.emitted_at
) TO STDOUT WITH (FORMAT csv, HEADER);
COMMIT;""")


if __name__ == "__main__":
    main()
