SET statement_timeout='60s';
-- snapshot cadence by age bucket (sample of mints created 20-26h ago)
WITH t AS (SELECT mint, created_at FROM meme_tokens WHERE created_at BETWEEN now() - interval '26 hours' AND now() - interval '20 hours' AND created_at IS NOT NULL LIMIT 3000),
s AS (SELECT t.mint, extract(epoch FROM s.observed_at - t.created_at) AS age, s.source FROM t JOIN meme_curve_snapshots_2026_09 s ON s.mint=t.mint AND s.observed_at BETWEEN t.created_at AND t.created_at + interval '6 hours')
SELECT width_bucket(age, ARRAY[0,60,120,300,600,1800,3600,7200,21600]) AS b, source, count(*) AS rows, count(DISTINCT mint) AS mints FROM s GROUP BY 1,2 ORDER BY 1,2;
-- how many mints have any snapshot; f15s coverage
SELECT count(*) AS tokens, count(*) FILTER (WHERE EXISTS (SELECT 1 FROM meme_curve_snapshots_2026_09 s WHERE s.mint=t.mint AND s.observed_at BETWEEN t.created_at AND t.created_at + interval '6 hours')) AS with_snap,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM meme_features_15s_2026_09 f WHERE f.mint=t.mint AND f.as_of BETWEEN t.created_at AND t.created_at + interval '1 hour' AND f.mcap_sol IS NOT NULL)) AS with_f15
FROM (SELECT mint, created_at FROM meme_tokens WHERE created_at BETWEEN now() - interval '26 hours' AND now() - interval '20 hours' LIMIT 3000) t;
