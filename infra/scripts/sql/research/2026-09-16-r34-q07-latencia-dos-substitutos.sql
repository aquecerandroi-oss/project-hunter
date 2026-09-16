-- R34 q07 — latencia de cada substituto da fita (fatia de 2 h, 15/09 BRT 18h-20h).
\set d0 '2026-09-15 21:00+00'
\set d1 '2026-09-15 23:00+00'
SET statement_timeout = 60000;
WITH s AS (
  SELECT mint, source, observed_at, received_at,
         observed_at - lag(observed_at) OVER (PARTITION BY mint ORDER BY observed_at) AS gap
  FROM meme_curve_snapshots
  WHERE observed_at >= timestamptz :'d0' AND observed_at < timestamptz :'d1'
)
SELECT 'curva ' || source AS substituto, count(*) AS linhas, count(DISTINCT mint) AS moedas,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM gap)))::numeric, 1) AS cadencia_mediana_s,
       round((percentile_cont(0.9) WITHIN GROUP (ORDER BY extract(epoch FROM gap)))::numeric, 1) AS cadencia_p90_s,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM received_at - observed_at)))::numeric, 2) AS atraso_mediano_s
FROM s GROUP BY 1
UNION ALL
SELECT 'foto usada pela linha 15s: ' || coalesce(snapshot_source, 'nulo'), count(*), count(DISTINCT mint), NULL, NULL,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM as_of - snapshot_observed_at)))::numeric, 2)
FROM meme_features_15s
WHERE as_of >= timestamptz :'d0' AND as_of < timestamptz :'d1' AND holders IS NOT NULL
GROUP BY 1
ORDER BY 2 DESC;
