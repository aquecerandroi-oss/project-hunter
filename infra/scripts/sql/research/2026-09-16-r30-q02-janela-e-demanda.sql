-- R30 16/09 17h20 BRT — janela do executor AGORA e na ULTIMA HORA (top 8 por demanda),
-- com desfecho de 1 min, top-10, creator_sold, criador serial, bundle do retrato e a fita
-- (compradores e maior comprador). Reuso literal do r23-q02.
-- Janela do radar: idade 30-300 s, progresso 0,02-0,50 (FRACAO), tape_reason IS NULL,
-- net_sol_flow_60s > 0, nao-Mayhem. Executor: progresso 5-50 % e snipers >= 21.
SET statement_timeout = 240000;

\echo == (a) AGORA: ultimos 5 min, uma linha por mint, por compradores
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

\echo == (c) ULTIMA HORA: melhor foto (por compradores) de cada moeda na janela — top 10
WITH janela AS (
  SELECT f.* FROM meme_features_15s f
  WHERE f.as_of >= now() - make_interval(mins => 60)
    AND f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.02 AND 0.50
    AND f.tape_reason IS NULL AND f.net_sol_flow_60s > 0
), melhor AS (
  SELECT DISTINCT ON (j.mint) j.* FROM janela j
  ORDER BY j.mint, j.unique_buyers_60s DESC NULLS LAST, j.net_sol_flow_60s DESC
)
SELECT t.symbol, left(m.mint,6), m.age_s, round(m.curve_progress_pct*100,1) AS prog, m.holders,
  m.unique_buyers_60s, m.buys_60s, m.sells_60s, round(m.net_sol_flow_60s,2) AS fluxo,
  round(m.curve_volume_60s_sol,1) AS vol60, m.snipers, round(m.dev_share*100,2) AS dev,
  m.creator_net_seller, left(t.creator,6),
  (SELECT count(*) FROM meme_tokens t2 WHERE t2.creator=t.creator
     AND t2.created_at >= now() - make_interval(days => 7)) AS criador_7d,
  t.completed_at IS NOT NULL AS encheu, t.migrated_at IS NOT NULL AS migrou,
  to_char(m.as_of AT TIME ZONE 'America/Sao_Paulo','HH24:MI') AS foto
FROM melhor m JOIN meme_tokens t ON t.mint=m.mint WHERE t.mayhem_mode IS NULL
ORDER BY m.unique_buyers_60s DESC NULLS LAST, m.net_sol_flow_60s DESC LIMIT 10;

\echo == (d) desfecho das 10: 1 min (prog, holders, top10, creator_sold), retrato (bundle/top10) e fita 90 min
WITH janela AS (
  SELECT f.mint, max(f.unique_buyers_60s) AS ub FROM meme_features_15s f
  JOIN meme_tokens t ON t.mint=f.mint AND t.mayhem_mode IS NULL
  WHERE f.as_of >= now() - make_interval(mins => 60)
    AND f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.02 AND 0.50
    AND f.tape_reason IS NULL AND f.net_sol_flow_60s > 0
  GROUP BY 1 ORDER BY 2 DESC NULLS LAST LIMIT 10
), dep AS (
  SELECT DISTINCT ON (f.mint) f.mint, f.curve_progress_pct, f.holders, f.top10_share,
         f.creator_sold, f.mcap_sol, f.end_time
  FROM meme_features_1m f JOIN janela ON janela.mint=f.mint
  WHERE f.end_time >= now() - make_interval(mins => 90)
  ORDER BY f.mint, f.end_time DESC
), ret AS (
  SELECT DISTINCT ON (r.mint) r.mint, r.bundled_share, r.top10_share AS top10_ret, r.observed_at
  FROM meme_risk_snapshots r JOIN janela ON janela.mint=r.mint
  ORDER BY r.mint, r.observed_at DESC
), tr AS (
  SELECT r.mint, r.trader, sum(r.sol_lamports)/1e9 AS sol FROM meme_trades r
  JOIN janela ON janela.mint=r.mint
  WHERE r.side='buy' AND r.block_time >= now() - make_interval(mins => 90) GROUP BY 1,2
), tot AS (SELECT mint, sum(sol) AS total, count(*) AS n FROM tr GROUP BY 1),
mx AS (SELECT DISTINCT ON (mint) mint, sol FROM tr ORDER BY mint, sol DESC)
SELECT t.symbol, left(j.mint,6), j.ub AS compradores_pico,
  round(dep.curve_progress_pct*100,1) AS prog_agora, dep.holders AS holders_agora,
  round(dep.top10_share*100,1) AS top10_1m, dep.creator_sold, round(dep.mcap_sol,1) AS mcap,
  round(ret.bundled_share*100,1) AS bundle_ret, round(ret.top10_ret*100,1) AS top10_ret,
  to_char(ret.observed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI') AS retrato_em,
  tot.n AS compradores_fita, round(mx.sol/nullif(tot.total,0)*100,1) AS maior_comprador_pct,
  t.completed_at IS NOT NULL AS encheu,
  to_char(dep.end_time AT TIME ZONE 'America/Sao_Paulo','HH24:MI') AS ultima_foto
FROM janela j JOIN meme_tokens t ON t.mint=j.mint
LEFT JOIN dep ON dep.mint=j.mint LEFT JOIN ret ON ret.mint=j.mint
LEFT JOIN tot ON tot.mint=j.mint LEFT JOIN mx ON mx.mint=j.mint
ORDER BY j.ub DESC;
