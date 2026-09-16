-- R37 (T4.40) — Quanto a linha de 15 s está atrasada em relação ao relógio do instante.
-- Janela: 16/09/2026 16:00–18:00 BRT (19:00–21:00 UTC). Lê só meme_features_15s.
-- Mede as_of - snapshot_observed_at (a idade da foto que a linha carrega) por fonte.
SELECT coalesce(snapshot_source, '(sem foto)')                                  AS fonte,
       count(*)                                                                 AS linhas,
       round(percentile_disc(0.50) WITHIN GROUP (
           ORDER BY extract(epoch FROM (as_of - snapshot_observed_at)))::numeric, 1) AS p50_s,
       round(percentile_disc(0.90) WITHIN GROUP (
           ORDER BY extract(epoch FROM (as_of - snapshot_observed_at)))::numeric, 1) AS p90_s,
       round(percentile_disc(0.99) WITHIN GROUP (
           ORDER BY extract(epoch FROM (as_of - snapshot_observed_at)))::numeric, 1) AS p99_s,
       round(max(extract(epoch FROM (as_of - snapshot_observed_at)))::numeric, 1)    AS max_s,
       count(*) FILTER (WHERE as_of - snapshot_observed_at > interval '60 seconds') AS acima_60s,
       count(*) FILTER (WHERE as_of - snapshot_observed_at > interval '120 seconds') AS acima_120s
FROM meme_features_15s
WHERE as_of >= timestamptz '2026-09-16 19:00:00+00'
  AND as_of <  timestamptz '2026-09-16 21:00:00+00'
  AND snapshot_observed_at IS NOT NULL
GROUP BY 1
ORDER BY 2 DESC;
