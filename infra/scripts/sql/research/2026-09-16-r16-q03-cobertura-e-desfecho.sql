-- KB-0107 Q03 — diagnostico de cobertura da simulacao de saida da Q01.
-- Para as entradas da porta L (variante L1b, sem teto de progresso), quantas
-- barras de 1 min existem no horizonte de :hz min depois da entrada, e o que
-- aconteceu com a moeda (graduou / migrou / serie simplesmente acaba).
-- Uso: psql -v dia=2026-09-15 -v janela=30 -v hz=30 -A -F '|' -f -
SET statement_timeout = 60000;
WITH bounds AS (
  SELECT (:'dia')::date::timestamp AT TIME ZONE 'America/Sao_Paulo' AS d0,
         ((:'dia')::date + 1)::timestamp AT TIME ZONE 'America/Sao_Paulo' AS d1
), tok AS (
  SELECT t.mint, t.created_at, t.completed_at, t.migrated_at
  FROM meme_tokens t, bounds b
  WHERE t.created_at >= b.d0 - interval '6 hours' AND t.created_at < b.d1
    AND t.mayhem_enabled IS NOT NULL AND NOT t.mayhem_enabled AND t.mayhem_mode IS NULL
    AND NOT (t.completed_at IS NOT NULL AND t.completed_at - t.created_at <= interval '60 seconds')
), lentas AS (
  SELECT k.*, x.at_30 FROM tok k CROSS JOIN LATERAL (
    SELECT min(cs.observed_at) AS at_30 FROM meme_curve_snapshots cs
    WHERE cs.mint = k.mint AND cs.real_sol_reserves >= 30) x
  WHERE x.at_30 IS NOT NULL AND x.at_30 >= k.created_at + interval '180 seconds'
), entrada AS (
  SELECT DISTINCT ON (l.mint) l.mint, l.completed_at, l.migrated_at,
         b.end_time AS t_in, b.mcap_sol AS base
  FROM lentas l
  JOIN meme_features_1m b ON b.mint = l.mint AND b.end_time >= l.at_30
   AND b.end_time <= l.at_30 + make_interval(mins => (:'janela')::int)
   AND b.end_time >= l.created_at + interval '180 seconds'
  CROSS JOIN bounds bb
  WHERE b.end_time >= bb.d0 AND b.end_time < bb.d1
    AND b.mcap_sol IS NOT NULL AND b.mcap_sol > 0
    AND (l.completed_at IS NULL OR l.completed_at > b.end_time)
    AND (l.migrated_at IS NULL OR l.migrated_at > b.end_time)
    AND b.curve_progress_pct IS NOT NULL
    AND b.tape_reason IS NULL AND b.net_sol_flow_1m > 0
  ORDER BY l.mint, b.end_time
), cob AS (
  SELECT e.mint, e.completed_at, e.migrated_at, e.t_in,
         (SELECT count(*) FROM meme_features_1m s WHERE s.mint = e.mint
            AND s.end_time > e.t_in AND s.end_time <= e.t_in + make_interval(mins => (:'hz')::int)
            AND s.mcap_sol IS NOT NULL) AS barras
  FROM entrada e
)
SELECT :'dia' AS dia, count(*) AS entradas,
  count(*) FILTER (WHERE barras = 0) AS sem_barra,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY barras)::numeric,1) AS barras_mediana,
  count(*) FILTER (WHERE barras >= 25) AS cobertura_cheia,
  count(*) FILTER (WHERE completed_at IS NOT NULL
                     AND completed_at <= t_in + make_interval(mins => (:'hz')::int)) AS graduou_no_horizonte,
  count(*) FILTER (WHERE completed_at IS NOT NULL) AS graduou_um_dia,
  count(*) FILTER (WHERE barras < 25 AND completed_at IS NULL) AS serie_acaba_sem_graduar
FROM cob;
