-- KB-0099 Q04 — o que as moedas fizeram DEPOIS da foto que passou a porta.
-- Duas coortes no mesmo dia BRT:
--   A "passa_tudo"  : existe foto de 15 s com os 13 criterios de operator/5;
--   B "so_subindo"  : nunca ha foto completa, mas ha foto em que as UNICAS
--                     recusas sao 12 (holders nao caindo) e/ou 13 (progresso
--                     subindo) -- as duas que dependem de duas fotos de 15 s.
-- Base = mcap_sol da foto de entrada; janelas de 5/15/30 min na propria serie
-- de 15 s. Unidades: curve_progress_pct e FRACAO nesta tabela.
-- Uso: psql -v dia=2026-09-15 -f este-arquivo.sql
SET statement_timeout = 60000;

WITH linhas AS (
  SELECT f.mint, f.as_of, f.mcap_sol, f.curve_progress_pct, f.progress_rising, f.mcap_delta_60s,
         f.holders, f.holders_prev, f.holders_rising, f.buys_60s, f.sells_60s,
         f.unique_buyers_60s, f.net_sol_flow_60s, f.curve_volume_60s_sol,
         f.creator_net_seller, f.dev_share, f.snipers,
         t.mayhem_enabled, t.completed_at, t.migrated_at
  FROM meme_features_15s f
  JOIN meme_tokens t ON t.mint = f.mint
  WHERE f.as_of >= (:'dia')::date::timestamp AT TIME ZONE 'America/Sao_Paulo'
    AND f.as_of <  ((:'dia')::date + 1)::timestamp AT TIME ZONE 'America/Sao_Paulo'
    AND f.age_s BETWEEN 30 AND 300
), marcada AS (
  SELECT mint, as_of, mcap_sol,
    ((completed_at IS NULL OR completed_at > as_of) AND (migrated_at IS NULL OR migrated_at > as_of)
      AND mayhem_enabled IS NOT NULL AND NOT mayhem_enabled
      AND curve_progress_pct BETWEEN 0.05 AND 0.50
      AND (creator_net_seller IS FALSE OR (creator_net_seller IS NULL AND dev_share IS NOT NULL AND dev_share <= 0.10))
      AND curve_volume_60s_sol >= 5 AND dev_share <= 0.10 AND snipers <= 10
      AND (CASE WHEN net_sol_flow_60s IS NOT NULL THEN net_sol_flow_60s > 0
                WHEN mcap_delta_60s IS NOT NULL THEN mcap_delta_60s > 0 ELSE false END)
      AND unique_buyers_60s >= 10
      AND buys_60s > 0 AND sells_60s::numeric / buys_60s <= 0.6
      AND holders >= 20) IS TRUE AS base_ok,
    (holders_rising IS NOT NULL AND (holders_rising OR (holders_prev IS NOT NULL AND holders >= holders_prev))) IS TRUE AS c12,
    COALESCE(progress_rising IS TRUE OR mcap_delta_60s > 0, false) AS c13
  FROM linhas
), coorte AS (
  SELECT mint,
         CASE WHEN bool_or(base_ok AND c12 AND c13) THEN 'A passa_tudo' ELSE 'B so_subindo' END AS coorte,
         CASE WHEN bool_or(base_ok AND c12 AND c13)
              THEN min(as_of) FILTER (WHERE base_ok AND c12 AND c13)
              ELSE min(as_of) FILTER (WHERE base_ok) END AS t0
  FROM marcada
  WHERE base_ok
  GROUP BY mint
), entrada AS (
  SELECT c.mint, c.coorte, c.t0, m.mcap_sol AS base
  FROM coorte c
  JOIN marcada m ON m.mint = c.mint AND m.as_of = c.t0
  WHERE m.mcap_sol > 0
), futuro AS (
  -- A serie de 15 s so existe enquanto age_s <= 300; o futuro de 5/15/30 min
  -- vem da serie de minuto (meme_features_1m.mcap_sol, barra fechada).
  SELECT e.mint, e.coorte, e.base,
    max(s.mcap_sol) FILTER (WHERE s.end_time <= e.t0 + interval '5 minutes')  AS max5,
    max(s.mcap_sol) FILTER (WHERE s.end_time <= e.t0 + interval '15 minutes') AS max15,
    max(s.mcap_sol) FILTER (WHERE s.end_time <= e.t0 + interval '30 minutes') AS max30,
    min(s.mcap_sol) FILTER (WHERE s.end_time <= e.t0 + interval '30 minutes') AS min30,
    count(*) AS barras
  FROM entrada e
  JOIN meme_features_1m s ON s.mint = e.mint
   AND s.end_time > e.t0 AND s.end_time <= e.t0 + interval '30 minutes'
  WHERE s.mcap_sol IS NOT NULL
  GROUP BY e.mint, e.coorte, e.base
)
SELECT :'dia' AS dia, coorte, count(*) AS moedas,
       count(*) FILTER (WHERE max5  >= 1.5 * base) AS ge_1_5x_5min,
       count(*) FILTER (WHERE max15 >= 1.5 * base) AS ge_1_5x_15min,
       count(*) FILTER (WHERE max30 >= 1.5 * base) AS ge_1_5x_30min,
       count(*) FILTER (WHERE max30 >= 3.0 * base) AS ge_3x_30min,
       count(*) FILTER (WHERE min30 <= 0.5 * base) AS queda_50_30min,
       round(avg(max30 / base), 3) AS mult_max_medio_30min,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY max30 / base)::numeric, 3) AS mult_max_mediana
FROM futuro GROUP BY coorte ORDER BY coorte;
