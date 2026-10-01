BEGIN READ ONLY;
SET LOCAL statement_timeout='60s';
SELECT c.relname, c.reltuples::bigint, pg_size_pretty(pg_relation_size(c.oid)) FROM pg_class c WHERE c.relname LIKE 'candles_1m_2026_%' ORDER BY 1;
COMMIT;
