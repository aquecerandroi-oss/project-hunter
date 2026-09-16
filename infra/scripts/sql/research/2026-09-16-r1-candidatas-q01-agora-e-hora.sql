-- R1 16/09 — candidatas dentro da janela do executor (idade 30-300 s, progresso 0,02-0,50 FRACAO,
-- fita presente = tape_reason IS NULL, net_sol_flow_60s > 0, nao-Mayhem = meme_tokens.mayhem_mode IS NULL).
-- Rodado na VPS via: docker exec -i <pg> psql -U hunter -d hunter -A -F "|" -f -
-- Unidades: meme_features_15s.curve_progress_pct e FRACAO 0-1; age_s so vai ate 300 nesta serie.

-- (a) funil instantaneo: ultima foto por mint nos ultimos 2 min
WITH ult AS (
  SELECT DISTINCT ON (f.mint) f.*
  FROM meme_features_15s f
  WHERE f.as_of >= now() - make_interval(mins => 2)
  ORDER BY f.mint, f.as_of DESC
)
SELECT count(*) AS mints_2min,
  count(*) FILTER (WHERE age_s BETWEEN 30 AND 300) AS na_idade,
  count(*) FILTER (WHERE age_s BETWEEN 30 AND 300 AND curve_progress_pct BETWEEN 0.02 AND 0.50) AS mais_progresso,
  count(*) FILTER (WHERE age_s BETWEEN 30 AND 300 AND curve_progress_pct BETWEEN 0.02 AND 0.50
                     AND tape_reason IS NULL) AS mais_fita,
  count(*) FILTER (WHERE age_s BETWEEN 30 AND 300 AND curve_progress_pct BETWEEN 0.02 AND 0.50
                     AND tape_reason IS NULL AND net_sol_flow_60s > 0) AS mais_fluxo
FROM ult;

-- (b) AGORA: ultimos 5 min, uma linha por mint, ordenado por demanda
WITH j AS (
  SELECT DISTINCT ON (f.mint) f.* FROM meme_features_15s f
  JOIN meme_tokens t ON t.mint = f.mint AND t.mayhem_mode IS NULL
  WHERE f.as_of >= now() - make_interval(mins => 5)
    AND f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.02 AND 0.50
    AND f.tape_reason IS NULL AND f.net_sol_flow_60s > 0
  ORDER BY f.mint, f.as_of DESC
)
SELECT t.symbol, left(j.mint,6) AS mint6, j.age_s, round(j.curve_progress_pct*100,1) AS prog_pct,
  j.holders, j.unique_buyers_60s AS compradores, j.buys_60s, j.sells_60s,
  round(j.net_sol_flow_60s,3) AS fluxo_sol, j.snipers, round(j.dev_share*100,2) AS dev_pct,
  j.creator_net_seller, j.holders_rising, j.progress_rising, left(t.creator,6) AS creator6,
  (SELECT count(*) FROM meme_tokens t2
     WHERE t2.creator = t.creator AND t2.created_at >= now() - interval '7 days') AS moedas_do_criador_7d,
  to_char(j.as_of AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS foto_brt
FROM j JOIN meme_tokens t ON t.mint = j.mint
ORDER BY j.unique_buyers_60s DESC NULLS LAST, j.net_sol_flow_60s DESC;

-- (c) ULTIMA HORA: melhor foto (por compradores) de cada moeda que esteve na janela
WITH janela AS (
  SELECT f.* FROM meme_features_15s f
  WHERE f.as_of >= now() - make_interval(mins => 60)
    AND f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.02 AND 0.50
    AND f.tape_reason IS NULL AND f.net_sol_flow_60s > 0
), melhor AS (
  SELECT DISTINCT ON (j.mint) j.* FROM janela j
  ORDER BY j.mint, j.unique_buyers_60s DESC NULLS LAST, j.net_sol_flow_60s DESC
)
SELECT t.symbol, left(m.mint,6) AS mint6, m.age_s, round(m.curve_progress_pct*100,1) AS prog_pct,
  m.holders, m.holders_rising, m.unique_buyers_60s AS compradores, m.buys_60s, m.sells_60s,
  round(m.net_sol_flow_60s,3) AS fluxo_sol, round(m.curve_volume_60s_sol,2) AS vol60,
  m.snipers, round(m.dev_share*100,2) AS dev_pct, m.creator_net_seller, m.progress_rising,
  left(t.creator,6) AS creator6,
  (SELECT count(*) FROM meme_tokens t2
     WHERE t2.creator=t.creator AND t2.created_at >= now() - interval '7 days') AS crt_7d,
  to_char(m.as_of AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS foto_brt
FROM melhor m JOIN meme_tokens t ON t.mint = m.mint
WHERE t.mayhem_mode IS NULL
ORDER BY m.unique_buyers_60s DESC NULLS LAST, m.net_sol_flow_60s DESC
LIMIT 40;
