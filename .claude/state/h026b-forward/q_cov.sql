BEGIN READ ONLY;
SET LOCAL statement_timeout='60s';
SELECT count(*) n, count(DISTINCT market_id) mk, min(open_time), max(open_time), sum(is_final::int) fin FROM candles_1d;
SELECT m.market_type, m.exchange_id, count(DISTINCT c.market_id) FROM candles_1d c JOIN markets m ON m.id=c.market_id GROUP BY 1,2;
SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p') AND c.relname LIKE 'spot%' ORDER BY 1;
COMMIT;
