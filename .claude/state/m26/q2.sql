SELECT source, count(*), count(DISTINCT mint) FROM meme_curve_snapshots WHERE observed_at > now() - interval '24 hours' GROUP BY 1;
-- age buckets of features_1m rows, last 72h
WITH f AS (
  SELECT f.mint, f.end_time, extract(epoch FROM f.end_time - t.created_at)/60.0 AS age_min,
         f.line_reason, f.distance_to_support_pct, f.mcap_sol, f.tape_reason, f.holders, f.curve_reason, f.line_points,
         t.completed_at, t.migrated_at
  FROM meme_features_1m f JOIN meme_tokens t ON t.mint = f.mint
  WHERE f.end_time > now() - interval '72 hours' AND f.features_version = 'meme_features_v3' AND t.created_at IS NOT NULL
)
SELECT CASE WHEN age_min < 5 THEN 'a <5' WHEN age_min < 15 THEN 'b 5-15' WHEN age_min < 30 THEN 'c 15-30'
            WHEN age_min < 60 THEN 'd 30-60' WHEN age_min < 120 THEN 'e 60-120' WHEN age_min < 240 THEN 'f 120-240'
            WHEN age_min < 1440 THEN 'g 4h-24h' ELSE 'h >24h' END AS age,
       count(*) AS rows_, count(DISTINCT mint) AS mints,
       round(avg((mcap_sol IS NOT NULL)::int),3) AS has_mcap,
       round(avg((distance_to_support_pct IS NOT NULL)::int),3) AS has_line,
       round(avg((line_reason='flat')::int),3) AS flat,
       round(avg((line_reason='too_few_points')::int),3) AS few,
       round(avg((line_reason='no_snapshot')::int),3) AS nosnap,
       round(avg((tape_reason IS NULL)::int),3) AS has_tape,
       round(avg((holders IS NOT NULL)::int),3) AS has_holders,
       percentile_disc(0.5) WITHIN GROUP (ORDER BY line_points) AS pts_p50,
       round(avg((migrated_at IS NOT NULL AND migrated_at <= end_time)::int),3) AS migrated
FROM f GROUP BY 1 ORDER BY 1;
