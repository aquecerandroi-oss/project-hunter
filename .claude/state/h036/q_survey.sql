-- h036 — inventário cego (nenhum desfecho): o que de livro existe no banco, retenção e cobertura.
BEGIN READ ONLY;
SET LOCAL statement_timeout='300s';
SELECT now() AS agora;
SELECT c.relname, pg_size_pretty(pg_total_relation_size(c.oid)) AS tam
FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid JOIN pg_class p ON p.oid = i.inhparent
WHERE p.relname IN ('market_snapshots') ORDER BY 1;
SELECT min(ts), max(ts), count(*) AS linhas, count(spread_pct) AS com_spread, count(DISTINCT market_id) AS mercados FROM market_snapshots;
SELECT table_name, column_name, data_type FROM information_schema.columns
WHERE table_schema='public' AND (table_name IN ('market_snapshots','strategy_versions')
   OR column_name ILIKE '%spread%' OR column_name ILIKE '%bid%' OR column_name ILIKE '%depth%' OR column_name ILIKE '%book%')
ORDER BY table_name, ordinal_position;
SELECT st.key, sv.version, sv.status::text, sv.purpose::text, sv.activated_at, sv.created_at
FROM strategy_versions sv JOIN strategies st ON st.id = sv.strategy_id
WHERE st.key = 'mean_reversion' ORDER BY sv.created_at;
COMMIT;
