-- R30 16/09 17h27 BRT -- o instante da decisao: quem esta na porta AGORA (ultimos 3 min),
-- com retrato de risco e a fita (compradores unicos e fatia do maior comprador, KB-0103).
SET statement_timeout = 120000;

\echo == (a) na porta agora (ultimos 3 min, prog 5-85, snipers >= 21, holders >= 20, compr >= 10)
WITH j AS (
  SELECT DISTINCT ON (f.mint) f.*, t.symbol, t.creator FROM meme_features_15s f
  JOIN meme_tokens t ON t.mint=f.mint AND t.mayhem_mode IS NULL
  WHERE f.as_of >= now() - make_interval(mins => 3)
    AND f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.05 AND 0.85
    AND f.tape_reason IS NULL AND f.net_sol_flow_60s > 0
    AND f.holders >= 20 AND f.unique_buyers_60s >= 10 AND f.snipers >= 21
    AND f.dev_share <= 0.10 AND f.buys_60s > 0 AND f.sells_60s::numeric/f.buys_60s <= 0.6
    AND f.curve_volume_60s_sol >= 5
  ORDER BY f.mint, f.as_of DESC
), r AS (
  SELECT DISTINCT ON (s.mint) s.mint, s.bundled_share, s.top10_share, s.observed_at
  FROM meme_risk_snapshots s JOIN j ON j.mint=s.mint ORDER BY s.mint, s.observed_at DESC
), tr AS (
  SELECT x.mint, x.trader, sum(x.sol_lamports)/1e9 AS sol FROM meme_trades x JOIN j ON j.mint=x.mint
  WHERE x.side='buy' AND x.block_time >= now() - make_interval(mins => 30) GROUP BY 1,2
), tot AS (SELECT mint, sum(sol) AS total, count(*) AS n FROM tr GROUP BY 1),
mx AS (SELECT DISTINCT ON (mint) mint, sol FROM tr ORDER BY mint, sol DESC)
SELECT to_char(j.as_of AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS foto, j.symbol,
  left(j.mint,6) AS mint6, j.age_s, round(j.curve_progress_pct*100,1) AS prog, j.holders,
  j.unique_buyers_60s AS compr, j.buys_60s, j.sells_60s, round(j.net_sol_flow_60s,2) AS fluxo,
  round(j.curve_volume_60s_sol,1) AS vol60, j.snipers, round(j.dev_share*100,2) AS dev,
  round(r.bundled_share*100,1) AS bundle, round(r.top10_share*100,1) AS top10,
  extract(epoch FROM (now()-r.observed_at))::int AS retrato_idade_s,
  tot.n AS compradores_fita, round(mx.sol/nullif(tot.total,0)*100,1) AS maior_comprador_pct,
  (SELECT count(*) FROM meme_tokens t2 WHERE t2.creator=j.creator
     AND t2.created_at >= now() - make_interval(days => 7)) AS criador_7d
FROM j LEFT JOIN r ON r.mint=j.mint LEFT JOIN tot ON tot.mint=j.mint LEFT JOIN mx ON mx.mint=j.mint
ORDER BY j.unique_buyers_60s DESC NULLS LAST;

\echo == (b) NIKKI AYrp8o -- a candidata admitida pelo cenario II: serie de 1 min
SELECT to_char(end_time AT TIME ZONE 'America/Sao_Paulo','HH24:MI') AS min_brt,
  round(mcap_sol,1) AS mcap, round(curve_progress_pct*100,1) AS prog, holders,
  unique_buyers AS compr, round(top10_share*100,1) AS top10, creator_sold
FROM meme_features_1m WHERE mint LIKE 'AYrp8o%' ORDER BY end_time DESC LIMIT 8;

\echo == (c) NIKKI: fita de 30 min (compradores e maior comprador)
WITH tr AS (
  SELECT trader, sum(sol_lamports)/1e9 AS sol FROM meme_trades
  WHERE mint LIKE 'AYrp8o%' AND side='buy' AND block_time >= now() - make_interval(mins => 30)
  GROUP BY 1
)
SELECT count(*) AS compradores, round(sum(sol),2) AS sol_total,
  round(max(sol)/nullif(sum(sol),0)*100,1) AS maior_comprador_pct FROM tr;
