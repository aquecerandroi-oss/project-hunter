-- R86 — cadastro de mercados (id → exchange, símbolo, tipo), para congelar `exchange = binance` (emenda 03:02Z).
BEGIN READ ONLY;
SET LOCAL statement_timeout='60s';
COPY (SELECT m.id AS market_id, e.code::text AS exchange, m.symbol, m.market_type::text AS market_type FROM markets m JOIN exchanges e ON e.id = m.exchange_id ORDER BY m.id)
TO STDOUT WITH (FORMAT csv, HEADER);
COMMIT;
