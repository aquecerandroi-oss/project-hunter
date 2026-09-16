-- R35 16/09 17h50 BRT -- janela do executor AGORA e na ULTIMA HORA (CONGELADA 16:50-17:50 BRT),
-- top 8 por demanda, com holders/compradores/fluxo/snipers/dev/creator_sold/top-10/bundle do retrato
-- (<= 600 s) e a fita. DESFECHO PELA CADEIA (real_sol_reserves pico/atual), nunca por mcap_sol -- KB-0115.
SET statement_timeout = 240000;

\echo == (a) AGORA: ultimos 5 min, uma linha por mint, por compradores (radar 2-50 %)
WITH j AS (
  SELECT DISTINCT ON (f.mint) f.* FROM meme_features_15s f
  JOIN meme_tokens t ON t.mint = f.mint AND t.mayhem_mode IS NULL
  WHERE f.as_of >= now() - make_interval(mins => 5)
    AND f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.02 AND 0.50
    AND f.tape_reason IS NULL AND f.net_sol_flow_60s > 0
  ORDER BY f.mint, f.as_of DESC
)
SELECT t.symbol, left(j.mint,6), j.age_s, round(j.curve_progress_pct*100,1) AS prog,
  j.holders, j.unique_buyers_60s, j.buys_60s, j.sells_60s,
  round(j.net_sol_flow_60s,2) AS fluxo, round(j.curve_volume_60s_sol,1) AS vol60,
  j.snipers, round(j.dev_share*100,2) AS dev, j.creator_net_seller, left(t.creator,6),
  (SELECT count(*) FROM meme_tokens t2 WHERE t2.creator=t.creator
     AND t2.created_at >= now() - make_interval(days => 7)) AS criador_7d,
  to_char(j.as_of AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS foto
FROM j JOIN meme_tokens t ON t.mint=j.mint
ORDER BY j.unique_buyers_60s DESC NULLS LAST, j.net_sol_flow_60s DESC LIMIT 12;

\echo == (b) funil instantaneo (ultima foto por mint nos ultimos 2 min)
WITH ult AS (
  SELECT DISTINCT ON (f.mint) f.* FROM meme_features_15s f
  WHERE f.as_of >= now() - make_interval(mins => 2) ORDER BY f.mint, f.as_of DESC
)
SELECT count(*) AS mints_2min,
  count(*) FILTER (WHERE age_s BETWEEN 30 AND 300) AS na_idade,
  count(*) FILTER (WHERE age_s BETWEEN 30 AND 300 AND curve_progress_pct BETWEEN 0.02 AND 0.50) AS mais_prog,
  count(*) FILTER (WHERE age_s BETWEEN 30 AND 300 AND curve_progress_pct BETWEEN 0.02 AND 0.50
                     AND tape_reason IS NULL) AS mais_fita,
  count(*) FILTER (WHERE age_s BETWEEN 30 AND 300 AND curve_progress_pct BETWEEN 0.02 AND 0.50
                     AND tape_reason IS NULL AND net_sol_flow_60s > 0) AS mais_fluxo
FROM ult;

\echo == (c) AGORA na PORTA inteira (ultimos 5 min, prog 5-85, porta operator/5) com retrato e fita
WITH j AS (
  SELECT DISTINCT ON (f.mint) f.*, t.symbol, t.creator FROM meme_features_15s f
  JOIN meme_tokens t ON t.mint=f.mint AND t.mayhem_mode IS NULL
  WHERE f.as_of >= now() - make_interval(mins => 5)
    AND f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.05 AND 0.85
    AND f.tape_reason IS NULL AND f.net_sol_flow_60s > 0
    AND f.holders >= 20 AND f.unique_buyers_60s >= 10 AND f.snipers >= 21
    AND f.dev_share <= 0.10 AND f.buys_60s > 0 AND f.sells_60s::numeric/f.buys_60s <= 0.6
    AND f.curve_volume_60s_sol >= 5
  ORDER BY f.mint, f.as_of DESC
), r AS (
  SELECT DISTINCT ON (s.mint) s.mint, s.bundled_share, s.top10_share, s.observed_at
  FROM meme_risk_snapshots s JOIN j ON j.mint=s.mint AND s.observed_at <= j.as_of
  ORDER BY s.mint, s.observed_at DESC
), tr AS (
  SELECT x.mint, x.trader, sum(x.sol_lamports)/1e9 AS sol FROM meme_trades x JOIN j ON j.mint=x.mint
  WHERE x.side='buy' AND x.block_time >= now() - make_interval(mins => 30) GROUP BY 1,2
), tot AS (SELECT mint, sum(sol) AS total, count(*) AS n FROM tr GROUP BY 1),
mx AS (SELECT DISTINCT ON (mint) mint, sol FROM tr ORDER BY mint, sol DESC),
ch AS (
  SELECT DISTINCT ON (c.mint) c.mint, c.real_sol_reserves AS rsol_agora, c.mcap_sol,
    c.virtual_sol_reserves - c.real_sol_reserves AS invariante
  FROM meme_curve_snapshots c JOIN j ON j.mint=c.mint ORDER BY c.mint, c.observed_at DESC
), pk AS (SELECT c.mint, max(c.real_sol_reserves) AS rsol_pico FROM meme_curve_snapshots c
          JOIN j ON j.mint=c.mint GROUP BY 1)
SELECT to_char(j.as_of AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS foto, j.symbol,
  left(j.mint,6) AS mint6, j.age_s, round(j.curve_progress_pct*100,1) AS prog, j.holders,
  j.unique_buyers_60s AS compr, j.buys_60s, j.sells_60s, round(j.net_sol_flow_60s,2) AS fluxo,
  round(j.curve_volume_60s_sol,1) AS vol60, j.snipers, round(j.dev_share*100,2) AS dev,
  round(r.bundled_share*100,1) AS bundle, round(r.top10_share*100,1) AS top10,
  extract(epoch FROM (j.as_of-r.observed_at))::int AS retrato_idade_s,
  tot.n AS compradores_fita, round(mx.sol/nullif(tot.total,0)*100,1) AS maior_comprador_pct,
  (SELECT count(*) FROM meme_tokens t2 WHERE t2.creator=j.creator
     AND t2.created_at >= now() - make_interval(days => 7)) AS criador_7d,
  round(pk.rsol_pico,3) AS rsol_pico, round(ch.rsol_agora,3) AS rsol_agora,
  round(ch.invariante,3) AS invariante
FROM j LEFT JOIN r ON r.mint=j.mint LEFT JOIN tot ON tot.mint=j.mint LEFT JOIN mx ON mx.mint=j.mint
LEFT JOIN ch ON ch.mint=j.mint LEFT JOIN pk ON pk.mint=j.mint
ORDER BY j.unique_buyers_60s DESC NULLS LAST;

\echo == (d) ULTIMA HORA CONGELADA 16:50-17:50 BRT: melhor foto por moeda, top 10 por compradores
CREATE TEMP TABLE r35h AS
WITH janela AS (
  SELECT f.* FROM meme_features_15s f JOIN meme_tokens t ON t.mint=f.mint AND t.mayhem_mode IS NULL
  WHERE f.as_of >= timestamptz '2026-09-16 16:50-03' AND f.as_of < timestamptz '2026-09-16 17:50-03'
    AND f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.02 AND 0.50
    AND f.tape_reason IS NULL AND f.net_sol_flow_60s > 0
), melhor AS (
  SELECT DISTINCT ON (j.mint) j.* FROM janela j
  ORDER BY j.mint, j.unique_buyers_60s DESC NULLS LAST, j.net_sol_flow_60s DESC
)
SELECT * FROM melhor ORDER BY unique_buyers_60s DESC NULLS LAST, net_sol_flow_60s DESC LIMIT 10;

SELECT t.symbol, left(m.mint,6) AS mint6, m.age_s, round(m.curve_progress_pct*100,1) AS prog, m.holders,
  m.unique_buyers_60s AS compr, m.buys_60s, m.sells_60s, round(m.net_sol_flow_60s,2) AS fluxo,
  round(m.curve_volume_60s_sol,1) AS vol60, m.snipers, round(m.dev_share*100,2) AS dev,
  left(t.creator,6) AS criador,
  (SELECT count(*) FROM meme_tokens t2 WHERE t2.creator=t.creator
     AND t2.created_at >= now() - make_interval(days => 7)) AS criador_7d,
  to_char(m.as_of AT TIME ZONE 'America/Sao_Paulo','HH24:MI') AS foto
FROM r35h m JOIN meme_tokens t ON t.mint=m.mint
ORDER BY m.unique_buyers_60s DESC NULLS LAST, m.net_sol_flow_60s DESC;

\echo == (e) as 10: retrato (<= 600 s), creator_sold, top-10 de 1 min, fita e DESFECHO PELA CADEIA
WITH ret AS (
  SELECT DISTINCT ON (h.mint) h.mint, r.bundled_share, r.top10_share AS top10_ret,
    extract(epoch FROM (h.as_of - r.observed_at))::int AS retrato_idade_s
  FROM r35h h JOIN meme_risk_snapshots r ON r.mint=h.mint AND r.observed_at <= h.as_of
  ORDER BY h.mint, r.observed_at DESC
), um AS (
  SELECT DISTINCT ON (h.mint) h.mint, f.top10_share, f.creator_sold, f.holders AS holders_1m
  FROM r35h h JOIN meme_features_1m f ON f.mint=h.mint ORDER BY h.mint, f.end_time DESC
), tr AS (
  SELECT x.mint, x.trader, sum(x.sol_lamports)/1e9 AS sol FROM meme_trades x JOIN r35h h ON h.mint=x.mint
  WHERE x.side='buy' AND x.block_time >= timestamptz '2026-09-16 16:40-03' GROUP BY 1,2
), tot AS (SELECT mint, sum(sol) AS total, count(*) AS n FROM tr GROUP BY 1),
mx AS (SELECT DISTINCT ON (mint) mint, sol FROM tr ORDER BY mint, sol DESC),
pk AS (SELECT c.mint, max(c.real_sol_reserves) AS rsol_pico FROM meme_curve_snapshots c
       JOIN r35h h ON h.mint=c.mint GROUP BY 1),
ag AS (SELECT DISTINCT ON (c.mint) c.mint, c.real_sol_reserves AS rsol_agora, c.mcap_sol,
         c.complete, c.mayhem_enabled, c.virtual_sol_reserves-c.real_sol_reserves AS invariante,
         c.observed_at
       FROM meme_curve_snapshots c JOIN r35h h ON h.mint=c.mint ORDER BY c.mint, c.observed_at DESC)
SELECT t.symbol, left(h.mint,6) AS mint6, h.unique_buyers_60s AS compr,
  round(ret.bundled_share*100,1) AS bundle_ret, round(ret.top10_ret*100,1) AS top10_ret,
  ret.retrato_idade_s, round(um.top10_share*100,1) AS top10_1m, um.creator_sold, um.holders_1m,
  tot.n AS compradores_fita, round(mx.sol/nullif(tot.total,0)*100,1) AS maior_comprador_pct,
  round(pk.rsol_pico,3) AS rsol_pico, round(ag.rsol_agora,3) AS rsol_agora,
  round(100*(ag.rsol_agora/nullif(pk.rsol_pico,0)-1),1) AS delta_rsol_pct,
  round(ag.mcap_sol,1) AS mcap_agora, ag.complete AS encheu, ag.mayhem_enabled,
  round(ag.invariante,3) AS invariante,
  to_char(ag.observed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI') AS ultima_leitura
FROM r35h h JOIN meme_tokens t ON t.mint=h.mint
LEFT JOIN ret ON ret.mint=h.mint LEFT JOIN um ON um.mint=h.mint
LEFT JOIN tot ON tot.mint=h.mint LEFT JOIN mx ON mx.mint=h.mint
LEFT JOIN pk ON pk.mint=h.mint LEFT JOIN ag ON ag.mint=h.mint
ORDER BY h.unique_buyers_60s DESC NULLS LAST;
