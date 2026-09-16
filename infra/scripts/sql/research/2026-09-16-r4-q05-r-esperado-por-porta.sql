-- KB-0099 Q05 — R esperado medido nos dados para uma porta parametrizada.
-- Entrada: a PRIMEIRA foto de 15 s do dia (idade 30-300 s) que passa a porta.
-- Saida simulada na serie de minuto (meme_features_1m.mcap_sol), horizonte
-- 10 min: alvo 3x, trailing 35 % depois de 1,5x, piso -50 %, taxa 1,75 % por
-- perna. R = (multiplo liquido - 1) / 0,5 (a unidade de risco e o piso).
-- Fill pessimista: a saida por stop usa o mcap OBSERVADO na barra, nao o nivel.
-- Uso: psql -v dia=2026-09-15 -v rotulo=base -v snipers_max=10 -v holders_min=20
--        -v prog_min=0.05 -v prog_max=0.50 -v ratio_max=0.6 -v buyers_min=10
--        -v vol_min=5 -v subindo=1 -v pedigree=1 -f este-arquivo.sql
SET statement_timeout = 60000;

WITH linhas AS (
  SELECT f.mint, f.as_of, f.mcap_sol, f.curve_progress_pct, f.progress_rising, f.mcap_delta_60s,
         f.holders, f.holders_prev, f.holders_rising, f.buys_60s, f.sells_60s,
         f.unique_buyers_60s, f.net_sol_flow_60s, f.curve_volume_60s_sol,
         f.creator_net_seller, f.dev_share, f.snipers,
         t.mayhem_enabled, t.completed_at, t.migrated_at, t.creator, t.symbol, t.created_at
  FROM meme_features_15s f
  JOIN meme_tokens t ON t.mint = f.mint
  WHERE f.as_of >= (:'dia')::date::timestamp AT TIME ZONE 'America/Sao_Paulo'
    AND f.as_of <  ((:'dia')::date + 1)::timestamp AT TIME ZONE 'America/Sao_Paulo'
    AND f.age_s BETWEEN 30 AND 300
), passa AS (
  SELECT mint, min(as_of) AS t0 FROM linhas
  WHERE (completed_at IS NULL OR completed_at > as_of)
    AND (migrated_at IS NULL OR migrated_at > as_of)
    AND mayhem_enabled IS NOT NULL AND NOT mayhem_enabled
    AND curve_progress_pct BETWEEN (:'prog_min')::numeric AND (:'prog_max')::numeric
    AND (creator_net_seller IS FALSE OR (creator_net_seller IS NULL AND dev_share IS NOT NULL AND dev_share <= 0.10))
    AND curve_volume_60s_sol >= (:'vol_min')::numeric
    AND dev_share <= 0.10
    AND snipers <= (:'snipers_max')::int
    AND (CASE WHEN net_sol_flow_60s IS NOT NULL THEN net_sol_flow_60s > 0
              WHEN mcap_delta_60s IS NOT NULL THEN mcap_delta_60s > 0 ELSE false END)
    AND unique_buyers_60s >= (:'buyers_min')::int
    AND buys_60s > 0 AND sells_60s::numeric / buys_60s <= (:'ratio_max')::numeric
    AND holders >= (:'holders_min')::int
    AND ((:'subindo')::int = 0 OR (
          holders_rising IS NOT NULL
          AND (holders_rising OR (holders_prev IS NOT NULL AND holders >= holders_prev))
          AND COALESCE(progress_rising IS TRUE OR mcap_delta_60s > 0, false)))
    AND mcap_sol > 0
  GROUP BY mint
), entrada AS (
  SELECT p.mint, p.t0, l.mcap_sol AS base
  FROM passa p
  JOIN linhas l ON l.mint = p.mint AND l.as_of = p.t0
  JOIN meme_tokens t ON t.mint = p.mint
  WHERE (:'pedigree')::int = 0 OR (
    t.creator IS NOT NULL AND t.created_at IS NOT NULL
    AND (SELECT count(*) FROM meme_tokens o WHERE o.creator = t.creator AND o.mint <> t.mint
           AND o.created_at IS NOT NULL AND o.created_at <= t.created_at
           AND o.created_at > t.created_at - interval '1 hour') <= 1
    AND (SELECT count(*) FROM meme_tokens o WHERE o.symbol = t.symbol AND o.mint <> t.mint
           AND o.created_at IS NOT NULL AND o.created_at <= t.created_at
           AND o.created_at > t.created_at - interval '24 hours') <= 2)
), barras AS (
  SELECT e.mint, e.t0, e.base, s.end_time, s.mcap_sol,
         row_number() OVER (PARTITION BY e.mint ORDER BY s.end_time) AS i,
         max(s.mcap_sol) OVER (PARTITION BY e.mint ORDER BY s.end_time
                               ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS pico_ate_anterior
  FROM entrada e
  JOIN meme_features_1m s ON s.mint = e.mint
   AND s.end_time > e.t0 AND s.end_time <= e.t0 + interval '10 minutes'
  WHERE s.mcap_sol IS NOT NULL
), gatilho AS (
  SELECT *,
    CASE WHEN COALESCE(pico_ate_anterior, base) >= 1.5 * base
         THEN greatest(0.65 * COALESCE(pico_ate_anterior, base), 0.5 * base)
         ELSE 0.5 * base END AS nivel_stop
  FROM barras
), saida AS (
  SELECT DISTINCT ON (mint) mint, base, i, mcap_sol, nivel_stop,
    CASE WHEN mcap_sol >= 3 * base THEN 3 * base ELSE mcap_sol END AS preco_saida,
    CASE WHEN mcap_sol >= 3 * base THEN 'alvo_3x' ELSE 'stop' END AS motivo
  FROM gatilho
  WHERE mcap_sol >= 3 * base OR mcap_sol <= nivel_stop
  ORDER BY mint, i
), fim AS (
  SELECT DISTINCT ON (mint) mint, base, mcap_sol AS preco_saida, 'tempo_10m' AS motivo
  FROM gatilho ORDER BY mint, i DESC
), res AS (
  SELECT e.mint,
         COALESCE(s.preco_saida, f.preco_saida) AS preco_saida,
         COALESCE(s.motivo, f.motivo) AS motivo, e.base
  FROM entrada e
  LEFT JOIN saida s ON s.mint = e.mint
  LEFT JOIN fim f ON f.mint = e.mint
  WHERE COALESCE(s.preco_saida, f.preco_saida) IS NOT NULL
), r AS (
  SELECT mint, motivo,
         (preco_saida / base) * 0.9825 * 0.9825 - 1 AS retorno,
         ((preco_saida / base) * 0.9825 * 0.9825 - 1) / 0.5 AS r_unidades
  FROM res
)
SELECT :'dia' AS dia, :'rotulo' AS porta,
       (SELECT count(*) FROM entrada) AS candidatos_dia,
       count(*) AS com_serie,
       count(*) FILTER (WHERE motivo = 'alvo_3x') AS saidas_3x,
       count(*) FILTER (WHERE motivo = 'stop') AS saidas_stop,
       count(*) FILTER (WHERE motivo = 'tempo_10m') AS saidas_tempo,
       round(avg(r_unidades), 3) AS r_medio,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY r_unidades)::numeric, 3) AS r_mediana,
       round(sum(r_unidades), 2) AS r_total,
       round(100.0 * count(*) FILTER (WHERE retorno > 0) / NULLIF(count(*), 0), 1) AS acerto_pct
FROM r;
