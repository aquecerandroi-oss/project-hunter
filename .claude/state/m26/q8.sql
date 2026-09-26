WITH f AS (
  SELECT f.*, extract(epoch FROM f.end_time - t.created_at) AS age_s
  FROM meme_features_1m f JOIN meme_tokens t ON t.mint = f.mint
  WHERE f.end_time >= '2026-09-12 15:04+00' AND f.end_time < '2026-09-20 01:24+00' AND f.features_version='meme_features_v3'
)
SELECT coalesce(creator_net_seller::text, 'NULL:'||creator_net_seller_reason) cns, coalesce(tape_reason,'(tape ok)') tr, count(*),
  percentile_disc(array[0.5,0.9]) within group (order by curve_volume_1m_sol) vol
FROM f WHERE age_s BETWEEN 300 AND 600 AND curve_progress_pct BETWEEN 0.02 AND 0.5 AND higher_lows AND breakout_15m AND distance_to_support_pct BETWEEN 0 AND 0.25
GROUP BY 1,2 ORDER BY 3 DESC;
