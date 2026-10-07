-- R90 / H-033 — disponibilidade CEGA (sem desfecho): esquema e tamanho das fontes de open interest.
BEGIN READ ONLY;
SET LOCAL statement_timeout='120s';
SELECT table_name, column_name, data_type FROM information_schema.columns
 WHERE table_schema='public' AND (table_name IN ('open_interest_history') OR column_name ILIKE '%open_interest%')
 ORDER BY 1,2;
SELECT count(*) n, count(open_interest) n_oi, count(open_interest_value) n_oiv, min(ts) t0, max(ts) t1, count(DISTINCT market_id) mkts
FROM open_interest_history;
SELECT relname, n_live_tup FROM pg_stat_user_tables WHERE relname ILIKE 'market_snapshots%' OR relname ILIKE '%outbox%' OR relname ILIKE 'feature_snapshots%' ORDER BY 1;
COMMIT;
