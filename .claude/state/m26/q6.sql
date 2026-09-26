WITH f AS (
  SELECT f.*, extract(epoch FROM f.end_time - t.created_at) AS age_s
  FROM meme_features_1m f JOIN meme_tokens t ON t.mint = f.mint
  WHERE f.end_time >= '2026-09-12 15:04+00' AND f.end_time < '2026-09-20 01:24+00' AND f.features_version='meme_features_v3'
), s AS (
  SELECT *,
    (age_s BETWEEN 300 AND 600) AS a,
    (curve_progress_pct BETWEEN 0.02 AND 0.50) AS p,
    (distance_to_support_pct IS NOT NULL) AS l,
    coalesce(higher_lows,false) AS hl,
    coalesce(breakout_15m,false) AS bo,
    (distance_to_support_pct BETWEEN 0 AND 0.25) AS d,
    (creator_net_seller = false) AS c,
    (curve_volume_1m_sol >= 5) AS v
  FROM f
)
SELECT
  count(*) AS all_rows,
  count(*) FILTER (WHERE a) AS age_ok,
  count(*) FILTER (WHERE a AND p) AS age_prog,
  count(*) FILTER (WHERE a AND p AND l) AS plus_line_exists,
  count(*) FILTER (WHERE a AND p AND l AND hl) AS plus_hl,
  count(*) FILTER (WHERE a AND p AND l AND hl AND bo) AS plus_bo,
  count(*) FILTER (WHERE a AND p AND l AND hl AND bo AND d) AS plus_band,
  count(*) FILTER (WHERE a AND p AND l AND hl AND bo AND d AND c) AS plus_creator,
  count(*) FILTER (WHERE a AND p AND l AND hl AND bo AND d AND c AND v) AS plus_vol5,
  count(DISTINCT mint) FILTER (WHERE a AND p AND l AND hl AND bo AND d) AS mints_band,
  count(*) FILTER (WHERE a AND p AND l AND hl AND bo AND d AND c AND v AND curve_volume_1m_sol IS NOT NULL) AS chk
FROM s;
-- the line state among age-ok progress-ok rows
WITH f AS (
  SELECT f.line_reason, f.breakout_15m, f.higher_lows, f.creator_net_seller_reason, f.curve_volume_1m_sol, extract(epoch FROM f.end_time - t.created_at) AS age_s, f.curve_progress_pct
  FROM meme_features_1m f JOIN meme_tokens t ON t.mint = f.mint
  WHERE f.end_time >= '2026-09-12 15:04+00' AND f.end_time < '2026-09-20 01:24+00' AND f.features_version='meme_features_v3'
)
SELECT coalesce(line_reason,'(line ok)') lr, count(*), round(avg((curve_volume_1m_sol>=5)::int),3) vol5, percentile_disc(0.5) within group (order by curve_volume_1m_sol) vol_p50
FROM f WHERE age_s BETWEEN 300 AND 600 AND curve_progress_pct BETWEEN 0.02 AND 0.50 GROUP BY 1 ORDER BY 2 DESC;
