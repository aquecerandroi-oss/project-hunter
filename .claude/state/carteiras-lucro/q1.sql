-- carteiras-lucro (05/10/2026) — fatos para o desenho; só leitura, limitado.
BEGIN READ ONLY;
SET LOCAL statement_timeout='90s';
\echo '== meme_wallet_trades / positions'
SELECT (SELECT count(*) FROM meme_wallet_trades) AS wallet_trades, (SELECT count(*) FROM meme_wallet_positions) AS wallet_positions;
\echo '== meme_trades ultimos 10 dias por fonte'
SELECT date_trunc('day', block_time)::date AS d, source, count(*) AS n, count(DISTINCT trader) AS traders, count(DISTINCT mint) AS mints
FROM meme_trades WHERE block_time >= now() - interval '10 days' GROUP BY 1,2 ORDER BY 1,2;
\echo '== meme_tokens criados por dia'
SELECT date_trunc('day', created_at)::date AS d, count(*) FROM meme_tokens WHERE created_at >= now() - interval '10 days' GROUP BY 1 ORDER BY 1;
\echo '== tamanho do banco e maiores relacoes'
SELECT pg_size_pretty(pg_database_size(current_database())) AS db;
SELECT c.relname, pg_size_pretty(sum(pg_total_relation_size(c.oid))) AS sz
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relkind IN ('r','p') AND c.relname LIKE 'meme_%'
GROUP BY 1 ORDER BY sum(pg_total_relation_size(c.oid)) DESC LIMIT 12;
\echo '== latencia das compras reais: evento -> proposta -> recebido -> enviado -> pouso'
SELECT count(*) AS n,
 percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM p.proposed_at - p.features_end_time)) AS ev_to_prop_p50,
 percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM o.received_at - p.proposed_at)) AS prop_to_recv_p50,
 percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM o.submitted_at - o.received_at)) AS recv_to_sub_p50,
 percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM (o.fill->>'block_time')::timestamptz - o.submitted_at)) AS sub_to_block_p50,
 percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM (o.fill->>'block_time')::timestamptz - p.features_end_time)) AS ev_to_block_p50,
 percentile_cont(0.9) WITHIN GROUP (ORDER BY extract(epoch FROM (o.fill->>'block_time')::timestamptz - p.features_end_time)) AS ev_to_block_p90,
 min(o.received_at) AS first, max(o.received_at) AS last
FROM meme_live_orders o JOIN meme_proposals p ON p.id = o.proposal_id
WHERE o.side='buy' AND o.status='confirmed' AND o.fill ? 'block_time' AND p.features_end_time IS NOT NULL
  AND o.received_at >= '2026-09-18 18:00Z';
COMMIT;
