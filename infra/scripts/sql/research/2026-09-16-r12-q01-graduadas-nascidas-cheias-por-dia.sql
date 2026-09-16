-- R12/Q01 (KB-0104) — por dia BRT (12-16/09), quantas "graduadas" nascem cheias.
-- Graduada = meme_tokens.completed_at IS NOT NULL (o mesmo contador da KB-0098/KB-0101).
-- Nascida cheia (rotulo da KB-0103, duas pernas):
--   D) completed_at - created_at <= 60 s  (carimbo de OBSERVACAO, nao tempo on-chain; ver KB-0103 §5), OU
--   F) nunca teve uma foto de 15 s com curve_progress_pct < 0,9 ANTES de encher (o radar nunca a viu subir).
-- Organica = graduada que nao cai em nenhuma das duas pernas.
-- Populacao nao-Mayhem (coalesce(mayhem_enabled,false)=false), a mesma convencao da KB-0098 §6.
-- Unidades: curve_progress_pct e FRACAO 0-1 nesta serie.
-- IC: Wilson 95 % sobre a fracao nascida cheia / graduadas do dia.
SET statement_timeout = 60000;
WITH g AS (
  SELECT t.mint, t.created_at, t.completed_at,
         (t.created_at AT TIME ZONE 'America/Sao_Paulo')::date AS dia_brt
  FROM meme_tokens t
  WHERE t.created_at >= (date '2026-09-12' AT TIME ZONE 'America/Sao_Paulo')
    AND t.created_at <  (date '2026-09-17' AT TIME ZONE 'America/Sao_Paulo')
    AND t.completed_at IS NOT NULL
    AND coalesce(t.mayhem_enabled, false) = false
), lab AS (
  SELECT g.*,
    (g.completed_at - g.created_at <= interval '60 seconds') AS perna_d_60s,
    NOT EXISTS (
      SELECT 1 FROM meme_features_15s f
      WHERE f.mint = g.mint AND f.as_of >= g.created_at AND f.as_of <= g.completed_at
        AND f.curve_progress_pct IS NOT NULL AND f.curve_progress_pct < 0.9
    ) AS perna_f_sem_subida
  FROM g
), d AS (
  SELECT dia_brt,
         count(*)::numeric AS graduadas,
         count(*) FILTER (WHERE perna_d_60s)::numeric AS so_d_60s,
         count(*) FILTER (WHERE perna_f_sem_subida)::numeric AS so_f_sem_subida,
         count(*) FILTER (WHERE perna_d_60s OR perna_f_sem_subida)::numeric AS nascidas_cheias,
         count(*) FILTER (WHERE NOT (perna_d_60s OR perna_f_sem_subida))::numeric AS organicas
  FROM lab GROUP BY 1
)
SELECT dia_brt, graduadas::int, so_d_60s::int, so_f_sem_subida::int,
       nascidas_cheias::int, organicas::int,
       round(100*nascidas_cheias/graduadas, 1) AS pct_nascidas_cheias,
       round(100*((nascidas_cheias + 1.920729) / (graduadas + 3.841459)
             - 1.959964/(graduadas + 3.841459)
               * sqrt(nascidas_cheias*(graduadas-nascidas_cheias)/graduadas + 0.9604)), 1) AS ic95_lo,
       round(100*((nascidas_cheias + 1.920729) / (graduadas + 3.841459)
             + 1.959964/(graduadas + 3.841459)
               * sqrt(nascidas_cheias*(graduadas-nascidas_cheias)/graduadas + 0.9604)), 1) AS ic95_hi
FROM d ORDER BY 1;
