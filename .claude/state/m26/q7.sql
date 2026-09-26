WITH f AS (
  SELECT f.curve_progress_pct, f.progress_reason, extract(epoch FROM f.end_time - t.created_at) AS age_s, f.end_time
  FROM meme_features_1m f JOIN meme_tokens t ON t.mint = f.mint
  WHERE f.end_time >= '2026-09-12 15:04+00' AND f.end_time < '2026-09-20 01:24+00' AND f.features_version='meme_features_v3'
)
SELECT date_trunc('day', end_time) d, coalesce(progress_reason,'(ok)') pr, count(*), percentile_disc(array[0.5,0.9,0.99]) within group (order by curve_progress_pct) q
FROM f WHERE age_s BETWEEN 300 AND 600 GROUP BY 1,2 ORDER BY 1,2;
