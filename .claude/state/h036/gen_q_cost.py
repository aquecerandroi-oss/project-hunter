"""h036 — gera q_cost.sql: insumos do instrumento de custo SÓ para os signal_ids já expostos no lab-cost-sweep
(cache/out.csv.gz, extração 2026-10-07 06:07Z). Nenhum desfecho fora desse conjunto é lido."""
import csv, gzip
from pathlib import Path
HERE = Path(__file__).parent
rows = csv.DictReader(gzip.open(HERE.parent / "lab-cost-sweep/cache/out.csv.gz", "rt", encoding="utf-8"))
ids = sorted(r["signal_id"] for r in rows if r["cohort"] == "prospective" and r["mt"] == "perpetual"
             and (r["strategy"] == "mean_reversion" or (r["strategy"], r["version"]) == ("momentum", "v3")))
arr = "{" + ",".join(ids) + "}"
sql = f"""-- h036 — instrumento de custo: spread cotado (market_snapshots, 1/min, bid/ask do bookTicker) na entrada e na saída,
-- e as velas 1 m da entrada para o modelo de preenchimento passivo. SÓ os {len(ids)} signal_ids expostos. Só leitura.
BEGIN READ ONLY;
SET LOCAL statement_timeout='600s';
COPY (
WITH s AS (
  SELECT o.signal_id, a.market_id, o.entry_ts, o.result::text AS result,
         (o.meta->'progress'->>'exit_bar_open')::timestamptz AS xbo,
         (o.meta->'progress'->>'exit_at_open')::boolean AS x_at_open,
         o.meta->'progress'->>'exit_bar_high' AS x_high, o.virtual_targets->>0 AS target1
  FROM signal_outcomes o JOIN agent_signals a ON a.id = o.signal_id
  WHERE o.signal_id = ANY('{arr}'::uuid[])
)
SELECT s.signal_id, s.result, s.entry_ts, s.xbo, s.x_at_open, s.x_high, s.target1,
       e0.spread_pct AS sp_in, e0.bid AS bid_in, e0.ask AS ask_in, em.spread_pct AS sp_in_m1, ep.spread_pct AS sp_in_p1,
       x0.spread_pct AS sp_out, x1.spread_pct AS sp_out_p1,
       c0.open AS c0_open, c0.low AS c0_low, c1.low AS c1_low, c2.low AS c2_low
FROM s
LEFT JOIN market_snapshots e0 ON e0.market_id = s.market_id AND e0.ts = s.entry_ts
LEFT JOIN market_snapshots em ON em.market_id = s.market_id AND em.ts = s.entry_ts - interval '1 minute'
LEFT JOIN market_snapshots ep ON ep.market_id = s.market_id AND ep.ts = s.entry_ts + interval '1 minute'
LEFT JOIN market_snapshots x0 ON x0.market_id = s.market_id AND x0.ts = s.xbo
LEFT JOIN market_snapshots x1 ON x1.market_id = s.market_id AND x1.ts = s.xbo + interval '1 minute'
LEFT JOIN candles c0 ON c0.market_id = s.market_id AND c0.timeframe = '1m' AND c0.is_final AND c0.open_time = s.entry_ts
LEFT JOIN candles c1 ON c1.market_id = s.market_id AND c1.timeframe = '1m' AND c1.is_final AND c1.open_time = s.entry_ts + interval '1 minute'
LEFT JOIN candles c2 ON c2.market_id = s.market_id AND c2.timeframe = '1m' AND c2.is_final AND c2.open_time = s.entry_ts + interval '2 minutes'
ORDER BY s.signal_id
) TO STDOUT WITH (FORMAT csv, HEADER);
COMMIT;
"""
(HERE / "q_cost.sql").write_text(sql, encoding="utf-8")
print(len(ids), "ids")
