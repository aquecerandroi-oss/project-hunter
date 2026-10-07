-- R90 / H-033 — export CEGO dos eventos de OI do outbox (binance): bucket, símbolo, inserção e despacho de cada
-- evento. Serve para conferir a JANELA inteira (não só a leitura corrente) onde o outbox ainda existe (26/09 →).
-- Sem agrupamento nem ordenação (a versão agrupada estourou 600 s); a agregação por (símbolo, bucket) é feita em
-- Python. Sem desfecho.
BEGIN READ ONLY;
SET LOCAL statement_timeout='1500s';
COPY (
SELECT split_part(o.payload->>'key', ':', 2) AS symbol,
       o.payload->'payload'->>'bucket_ts' AS b,
       o.created_at, o.dispatched_at
FROM outbox_events o
WHERE o.stream = 'market.derivatives' AND split_part(o.payload->>'key', ':', 1) = 'binance'
  AND o.payload->'payload'->>'bucket_ts' IS NOT NULL
) TO STDOUT WITH (FORMAT csv, HEADER);
COMMIT;
