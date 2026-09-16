-- R37 (T4.40) — Idade do estado da curva no instante da proposta: proposed_at - a foto que a
-- linha de 15 s carregava (features_end_time = as_of da linha). 16/09 12:00-21:00 UTC.
WITH p AS (
    SELECT id, mint, proposed_at, features_end_time
    FROM meme_proposals
    WHERE proposed_at >= timestamptz '2026-09-16 12:00:00+00'
      AND proposed_at <  timestamptz '2026-09-16 21:00:00+00'
), j AS (
    SELECT p.*, f.snapshot_observed_at, f.curve_progress_pct
    FROM p JOIN meme_features_15s f
      ON f.mint = p.mint AND f.as_of = p.features_end_time
)
SELECT count(*)                                                                    AS propostas,
       round(percentile_disc(0.50) WITHIN GROUP (ORDER BY extract(epoch FROM (proposed_at - snapshot_observed_at)))::numeric,1) AS p50_s,
       round(percentile_disc(0.90) WITHIN GROUP (ORDER BY extract(epoch FROM (proposed_at - snapshot_observed_at)))::numeric,1) AS p90_s,
       round(percentile_disc(0.99) WITHIN GROUP (ORDER BY extract(epoch FROM (proposed_at - snapshot_observed_at)))::numeric,1) AS p99_s,
       round(max(extract(epoch FROM (proposed_at - snapshot_observed_at)))::numeric,1)                                          AS max_s,
       count(*) FILTER (WHERE proposed_at - snapshot_observed_at > interval '20 seconds')  AS acima_20s,
       count(*) FILTER (WHERE proposed_at - snapshot_observed_at > interval '30 seconds')  AS acima_30s,
       count(*) FILTER (WHERE proposed_at - snapshot_observed_at > interval '60 seconds')  AS acima_60s
FROM j;
