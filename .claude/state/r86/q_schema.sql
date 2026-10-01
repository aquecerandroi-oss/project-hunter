BEGIN READ ONLY;
SET LOCAL statement_timeout='60s';
\d candles_1m
SELECT inhrelid::regclass FROM pg_inherits WHERE inhparent='candles_1m'::regclass ORDER BY 1 LIMIT 200;
EXPLAIN SELECT market_id, count(*) n, max(received_at) mr, max(open_time) lo
FROM candles_1m WHERE timeframe='1m' AND is_final AND open_time >= '2026-08-20' AND open_time < '2026-08-21' GROUP BY market_id;
COMMIT;
