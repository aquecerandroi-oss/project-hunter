-- R1 16/09 — o que a porta de encanamento produziria na ultima hora
-- Base: moedas nao-Mayhem dentro da janela do executor (idade 30-300 s, progresso 2-50 %, fita, fluxo > 0)

-- (a) funil da hora e as duas barras
WITH j AS (
  SELECT f.* FROM meme_features_15s f
  JOIN meme_tokens t ON t.mint = f.mint AND t.mayhem_mode IS NULL
  WHERE f.as_of >= now() - make_interval(mins => 60)
    AND f.age_s BETWEEN 30 AND 300
    AND f.curve_progress_pct BETWEEN 0.02 AND 0.50
)
SELECT
  count(DISTINCT mint) AS na_janela_idade_progresso,
  count(DISTINCT mint) FILTER (WHERE tape_reason IS NULL) AS com_fita,
  count(DISTINCT mint) FILTER (WHERE tape_reason IS NULL AND net_sol_flow_60s > 0) AS fluxo_pos,
  count(DISTINCT mint) FILTER (WHERE tape_reason IS NULL AND net_sol_flow_60s > 0
        AND holders >= 10 AND unique_buyers_60s >= 5
        AND snipers IS NOT NULL AND snipers <= 10
        AND dev_share IS NOT NULL AND dev_share <= 0.10) AS porta_frouxa_10_5,
  count(DISTINCT mint) FILTER (WHERE tape_reason IS NULL AND net_sol_flow_60s > 0
        AND holders >= 20 AND unique_buyers_60s >= 10
        AND snipers IS NOT NULL AND snipers <= 10
        AND dev_share IS NOT NULL AND dev_share <= 0.10) AS barra_20_10_sem_subindo,
  count(DISTINCT mint) FILTER (WHERE tape_reason IS NULL AND net_sol_flow_60s > 0
        AND holders >= 20 AND unique_buyers_60s >= 10
        AND snipers IS NOT NULL AND snipers <= 10
        AND dev_share IS NOT NULL AND dev_share <= 0.10
        AND holders_rising IS TRUE AND progress_rising IS TRUE) AS barra_atual_subindo
FROM j;

-- (b) onde cada criterio corta isoladamente (melhor foto por moeda)
WITH j AS (
  SELECT DISTINCT ON (f.mint) f.* FROM meme_features_15s f
  JOIN meme_tokens t ON t.mint = f.mint AND t.mayhem_mode IS NULL
  WHERE f.as_of >= now() - make_interval(mins => 60)
    AND f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.02 AND 0.50
    AND f.tape_reason IS NULL AND f.net_sol_flow_60s > 0
  ORDER BY f.mint, f.unique_buyers_60s DESC NULLS LAST
)
SELECT count(*) AS base,
  count(*) FILTER (WHERE holders >= 10) AS holders_ge10,
  count(*) FILTER (WHERE holders >= 20) AS holders_ge20,
  count(*) FILTER (WHERE unique_buyers_60s >= 5) AS compradores_ge5,
  count(*) FILTER (WHERE unique_buyers_60s >= 10) AS compradores_ge10,
  count(*) FILTER (WHERE snipers <= 10) AS snipers_le10,
  count(*) FILTER (WHERE snipers <= 2) AS snipers_le2,
  count(*) FILTER (WHERE snipers IS NULL) AS snipers_null,
  count(*) FILTER (WHERE dev_share <= 0.10) AS dev_le10,
  count(*) FILTER (WHERE dev_share IS NULL) AS dev_null,
  count(*) FILTER (WHERE holders_rising IS TRUE) AS holders_subindo,
  count(*) FILTER (WHERE progress_rising IS TRUE) AS progresso_subindo
FROM j;

-- (c) a lista nominal que a porta frouxa proporia, com pedigree do criador e desfecho
WITH j AS (
  SELECT DISTINCT ON (f.mint) f.* FROM meme_features_15s f
  JOIN meme_tokens t ON t.mint=f.mint AND t.mayhem_mode IS NULL
  WHERE f.as_of >= now() - make_interval(mins => 60)
    AND f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.02 AND 0.50
    AND f.tape_reason IS NULL AND f.net_sol_flow_60s > 0
    AND f.holders >= 10 AND f.unique_buyers_60s >= 5
    AND f.snipers <= 10 AND f.dev_share <= 0.10
  ORDER BY f.mint, f.as_of
)
SELECT t.symbol, left(j.mint,6) AS mint6, j.age_s, round(j.curve_progress_pct*100,1) AS prog,
  j.holders, j.unique_buyers_60s AS compr, round(j.net_sol_flow_60s,2) AS fluxo, j.snipers,
  round(j.dev_share*100,2) AS dev, j.holders_rising, j.progress_rising, left(t.creator,6) AS creator6,
  (SELECT count(*) FROM meme_tokens t2
     WHERE t2.creator=t.creator AND t2.created_at>=now()-interval '7 days') AS crt7d,
  t.completed_at IS NOT NULL AS encheu,
  to_char(j.as_of AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS brt
FROM j JOIN meme_tokens t ON t.mint=j.mint ORDER BY j.as_of;
