-- cohort: mints created 2026-09-24 00:00 -> 2026-09-25 00:00 UTC (>= 36h follow-up)
WITH c AS (
  SELECT mint, created_at FROM meme_tokens
  WHERE created_at >= '2026-09-24 00:00+00' AND created_at < '2026-09-25 00:00+00'
), r AS (
  SELECT f.mint, extract(epoch FROM f.end_time - c.created_at)/60.0 AS age_min, f.buys_1m, f.mcap_sol, f.curve_progress_pct
  FROM meme_features_1m f JOIN c ON c.mint = f.mint
  WHERE f.end_time >= '2026-09-24 00:00+00' AND f.end_time < '2026-09-26 12:00+00' AND f.features_version='meme_features_v3'
), per AS (
  SELECT mint, max(age_min) AS last_age,
         bool_or(age_min BETWEEN 14 AND 16 AND buys_1m > 0) AS alive15,
         bool_or(age_min BETWEEN 14 AND 16) AS row15,
         bool_or(age_min >= 30) AS r30, bool_or(age_min >= 60) AS r60, bool_or(age_min >= 120) AS r120
  FROM r GROUP BY mint
)
SELECT (SELECT count(*) FROM c) AS created,
       count(*) AS with_rows,
       percentile_disc(ARRAY[0.1,0.5,0.9,0.99]) WITHIN GROUP (ORDER BY last_age) AS last_age_q,
       count(*) FILTER (WHERE row15) AS row15, count(*) FILTER (WHERE alive15) AS alive15,
       count(*) FILTER (WHERE alive15 AND r30) AS alive15_r30,
       count(*) FILTER (WHERE alive15 AND r60) AS alive15_r60,
       count(*) FILTER (WHERE alive15 AND r120) AS alive15_r120,
       count(*) FILTER (WHERE r30) AS r30, count(*) FILTER (WHERE r60) AS r60, count(*) FILTER (WHERE r120) AS r120
FROM per;
