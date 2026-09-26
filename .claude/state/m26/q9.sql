WITH f AS (
  SELECT f.*, extract(epoch FROM f.end_time - t.created_at)/60.0 AS age_min, t.migrated_at, t.completed_at
  FROM meme_features_1m f JOIN meme_tokens t ON t.mint = f.mint
  WHERE f.end_time >= '2026-09-23 00:00+00' AND f.end_time < '2026-09-26 00:00+00' AND f.features_version='meme_features_v3'
)
SELECT CASE WHEN age_min < 15 THEN 'a 10-15' WHEN age_min < 20 THEN 'b 15-20' WHEN age_min < 30 THEN 'c 20-30' ELSE 'd 30-120' END age,
  count(*) rows_, count(DISTINCT mint) mints,
  count(*) FILTER (WHERE buys_1m >= 3) active_rows,
  count(DISTINCT mint) FILTER (WHERE buys_1m >= 3) active_mints,
  round(avg((distance_to_support_pct IS NOT NULL)::int) FILTER (WHERE buys_1m >= 3),3) line_ok_active,
  round(avg(higher_lows::int) FILTER (WHERE buys_1m >= 3),3) hl_active,
  round(avg(breakout_15m::int) FILTER (WHERE buys_1m >= 3),3) bo_active,
  count(*) FILTER (WHERE buys_1m>=3 AND higher_lows AND breakout_15m) hl_bo_rows,
  count(DISTINCT mint) FILTER (WHERE buys_1m>=3 AND higher_lows AND breakout_15m) hl_bo_mints,
  count(DISTINCT mint) FILTER (WHERE buys_1m>=3 AND higher_lows AND breakout_15m AND distance_to_support_pct BETWEEN 0 AND 0.25) band_mints,
  percentile_disc(array[0.25,0.5,0.75]) within group (order by distance_to_support_pct) FILTER (WHERE buys_1m >= 3) dist_q,
  percentile_disc(array[0.5,0.9]) within group (order by curve_volume_1m_sol) FILTER (WHERE buys_1m >= 3) vol_q,
  round(avg((creator_net_seller IS NULL)::int) FILTER (WHERE buys_1m >= 3),3) creator_unknown,
  round(avg((curve_progress_pct < 1)::int) FILTER (WHERE buys_1m >= 3),3) on_curve
FROM f WHERE age_min >= 10 AND age_min < 120 AND (migrated_at IS NULL OR migrated_at > end_time) AND (completed_at IS NULL OR completed_at > end_time)
GROUP BY 1 ORDER BY 1;
