-- R86 / H-027 — agregado diário CEGO (só preço/cobertura, sem desfecho) da partição 2026-10.
-- Por (mercado, dia UTC): nº de velas 1m finais, última chegada (received_at) e o fechamento da vela 23:59.
BEGIN READ ONLY;
SET LOCAL statement_timeout='600s';
COPY (
SELECT k.market_id, (k.open_time AT TIME ZONE 'UTC')::date AS day,
       count(*) AS n_final,
       max(k.received_at) AS max_recv,
       max(k.close) FILTER (WHERE (k.open_time AT TIME ZONE 'UTC')::time = time '23:59') AS close_2359
FROM candles_1m_2026_10 k
WHERE k.timeframe = '1m' AND k.is_final
GROUP BY 1, 2
ORDER BY 1, 2
) TO STDOUT WITH (FORMAT csv, HEADER);
COMMIT;
