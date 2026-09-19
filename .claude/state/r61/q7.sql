SET statement_timeout='120s';
WITH t AS (
  SELECT mint, created_at, completed_at, twitter IS NOT NULL AS has_tw, telegram IS NOT NULL AS has_tg, website IS NOT NULL AS has_ws, twitter_kind, twitter_reuse_count, social_observed_at
  FROM meme_tokens WHERE created_at BETWEEN now() - interval '72 hours' AND now() - interval '2 hours'
), f AS (
  SELECT f.mint, min(f.mcap_sol) FILTER (WHERE f.age_s <= 30) AS m0, max(f.mcap_sol) AS mx,
         (array_agg(f.mcap_sol ORDER BY f.as_of DESC))[1] AS m_last, count(*) AS n
  FROM meme_features_15s_2026_09 f JOIN t ON t.mint=f.mint AND f.as_of BETWEEN t.created_at AND t.created_at + interval '30 min'
  WHERE f.mcap_sol IS NOT NULL GROUP BY f.mint
), b AS (
  SELECT mint, max(kol_count) AS max_kol, bool_or(board IN ('graduating','movers')) AS reached_board
  FROM meme_board_observations_2026_09 WHERE observed_at > now() - interval '72 hours' GROUP BY mint
)
SELECT
  CASE WHEN has_tg AND has_tw THEN 'tw+tg' WHEN has_tw THEN 'tw only' WHEN has_tg THEN 'tg only' ELSE 'none' END AS ident,
  count(*) AS n,
  round(100.0*count(*) FILTER (WHERE social_observed_at IS NOT NULL)/count(*),1) AS pct_social_read,
  round(100.0*avg((f.mx >= 2*f.m0)::int),1) AS pct_2x_30min,
  round(100.0*avg((f.mx >= 3*f.m0)::int),1) AS pct_3x_30min,
  round(100.0*avg((f.mx >= 1.5*f.m0 AND f.m_last <= 0.5*f.mx)::int),1) AS pct_rug_after_pump,
  round(100.0*avg((completed_at IS NOT NULL)::int),2) AS pct_graduated,
  round(100.0*avg((b.reached_board)::int),1) AS pct_reached_board,
  round(100.0*avg((b.max_kol > 0)::int),1) AS pct_any_kol,
  count(f.mint) AS n_with_series
FROM t LEFT JOIN f ON f.mint=t.mint LEFT JOIN b ON b.mint=t.mint
GROUP BY 1 ORDER BY n DESC;
