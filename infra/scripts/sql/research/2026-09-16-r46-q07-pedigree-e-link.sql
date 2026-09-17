-- R46 q07: por que 7 das 10 nao foram propostas (pedigree aproximado) + estado agora das vivas (LINK, QAUNTITY)
SET statement_timeout = 200000;
\pset format unaligned
\pset fieldsep '|'
WITH m AS (
  SELECT t.* FROM meme_tokens t WHERE t.mint IN ('3tmKhPmo9NixC8nNZYztNR41GsyxzLifRUzUdeubpump','ChgZ7GkiYkyyfp1qBuNu2qgprPYC17DnvUqbyVrQpump','6XcZ6ds95n9XnHvfbCqDmvowcQtLNNofnYyjMjkAjse9','97CXCc6bg7rcWo14L2UktwyxEpBRPUJ9eeeDw1ERpump','7x8cE5AoELM3gnFDq8KL7qxArp5cmi4nCZeqB2DWpump','4TcftzQvXTwSEfsuWL75LLNQvdennvRsjmCh3VS5pump','4hFxr7x8ive2NiYvrNoBiKrrimVgVP9KV4YgTEHApump','7fWspNngkwZ4rN2XSJpvsXE14RRjcrRV6DKqaN4ppump','GFakEBdgdKDJhsCKauSkKVjHYPqHDBEY7SgJZEJDpump','9PyqygumGwmbaJn7sVZVyUzHzBH4ZMj5R5eNDceupump')
)
SELECT 'pedigree' AS q, m.symbol, left(m.mint,8) AS mint8, coalesce(m.pool,'-') AS pool, coalesce(m.mayhem_mode,'-') AS mayhem,
  (SELECT count(*) FROM meme_tokens o WHERE o.symbol=m.symbol AND o.mint<>m.mint AND o.created_at IS NOT NULL AND o.created_at <= m.created_at AND o.created_at > m.created_at - interval '24 hours') AS clones_simbolo_24h,
  (SELECT count(*) FROM meme_tokens o WHERE o.creator=m.creator AND o.mint<>m.mint AND o.created_at IS NOT NULL AND o.created_at <= m.created_at AND o.created_at > m.created_at - interval '1 hour') AS criador_1h,
  (SELECT count(*) FROM meme_tokens o WHERE o.creator=m.creator AND o.mint<>m.mint AND o.created_at IS NOT NULL AND o.created_at <= m.created_at AND o.created_at > m.created_at - interval '7 days') AS criador_7d,
  (SELECT count(*) FROM meme_proposals p WHERE p.mint=m.mint) AS propostas,
  (SELECT count(*) FROM meme_features_1m f WHERE f.mint=m.mint AND f.end_time >= timestamptz '2026-09-16 19:00-03') AS n1m,
  (SELECT string_agg(DISTINCT coalesce(f.creator_net_seller::text, f.creator_net_seller_reason), ',') FROM meme_features_15s f WHERE f.mint=m.mint) AS cns_15s,
  (SELECT string_agg(DISTINCT coalesce(f.creator_sold::text, f.creator_sold_reason), ',') FROM meme_features_1m f WHERE f.mint=m.mint AND f.end_time >= timestamptz '2026-09-16 19:00-03') AS creator_sold_1m,
  (SELECT count(*) FROM meme_trades tr WHERE tr.mint=m.mint AND tr.trader=m.creator AND tr.side='sell' AND tr.block_time >= timestamptz '2026-09-16 19:00-03') AS cr_sells_fita
FROM m ORDER BY m.created_at;
-- LINK e QAUNTITY agora (1 m ate agora + ultima foto da cadeia)
SELECT 'link_1m' AS q, to_char(f.end_time AT TIME ZONE 'America/Sao_Paulo','HH24:MI') AS brt, f.age_minutes, round(f.curve_progress_pct*100,1) AS prog, coalesce(f.progress_reason,'-') AS prog_reason, round(f.mcap_sol,2) AS mcap_sol, f.holders, f.unique_buyers AS compr, f.buys_1m, f.sells_1m, round(f.net_sol_flow_1m,2) AS fluxo, round(f.top10_share*100,1) AS top10, f.creator_sold, f.creator_net_seller AS cns, f.snipers, round(f.dev_share*100,2) AS dev
FROM meme_features_1m f WHERE f.mint='4TcftzQvXTwSEfsuWL75LLNQvdennvRsjmCh3VS5pump' AND f.end_time >= timestamptz '2026-09-16 21:40-03' ORDER BY f.end_time;
SELECT 'link_cadeia' AS q, to_char(c.observed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS brt, round(c.real_sol_reserves,3) AS rsol, round(c.virtual_sol_reserves - c.real_sol_reserves,1) AS inv, c.complete, c.source
FROM meme_curve_snapshots c WHERE c.mint='4TcftzQvXTwSEfsuWL75LLNQvdennvRsjmCh3VS5pump' AND c.observed_at >= timestamptz '2026-09-16 21:55-03' ORDER BY c.observed_at DESC LIMIT 5;
SELECT 'qauntity_1m' AS q, to_char(f.end_time AT TIME ZONE 'America/Sao_Paulo','HH24:MI') AS brt, f.age_minutes, round(f.curve_progress_pct*100,1) AS prog, round(f.mcap_sol,2) AS mcap_sol, f.holders, f.unique_buyers AS compr, round(f.net_sol_flow_1m,2) AS fluxo, round(f.top10_share*100,1) AS top10, f.creator_sold
FROM meme_features_1m f WHERE f.mint='GFakEBdgdKDJhsCKauSkKVjHYPqHDBEY7SgJZEJDpump' AND f.end_time >= timestamptz '2026-09-16 21:15-03' ORDER BY f.end_time DESC LIMIT 4;
SELECT 'symbol_link_24h' AS q, count(*) FROM meme_tokens WHERE symbol='LINK' AND created_at >= timestamptz '2026-09-15 21:44-03' AND created_at < timestamptz '2026-09-16 21:44:54-03';
