SET statement_timeout='120s';
WITH t AS (
  SELECT mint, created_at, completed_at, twitter IS NOT NULL AS has_tw, telegram IS NOT NULL AS has_tg, website IS NOT NULL AS has_ws, twitter_kind, twitter_reuse_count, social_observed_at, creator_initial_sol
  FROM meme_tokens WHERE created_at BETWEEN now() - interval '72 hours' AND now() - interval '2 hours' AND social_observed_at IS NOT NULL
), f AS (
  SELECT f.mint, (array_agg(f.mcap_sol ORDER BY f.as_of ASC))[1] AS m0, max(f.mcap_sol) AS mx,
         (array_agg(f.mcap_sol ORDER BY f.as_of DESC))[1] AS m_last, count(*) AS n, max(f.holders) AS max_holders
  FROM meme_features_15s_2026_09 f JOIN t ON t.mint=f.mint AND f.as_of BETWEEN t.created_at AND t.created_at + interval '30 min'
  WHERE f.mcap_sol IS NOT NULL GROUP BY f.mint
), b AS (
  SELECT mint, max(kol_count) AS max_kol, bool_or(board IN ('graduating','movers')) AS reached_board
  FROM meme_board_observations_2026_09 WHERE observed_at > now() - interval '72 hours' GROUP BY mint
)
SELECT grp, count(*) AS n,
  round(100.0*avg((f.mx >= 60)::int),1) AS pct_peak_ge_60sol,
  round(100.0*avg((f.mx >= 100)::int),1) AS pct_peak_ge_100sol,
  round(100.0*avg((f.mx >= 60 AND f.m_last <= 0.5*f.mx)::int),1) AS pct_rug_after_60,
  round(100.0*avg((completed_at IS NOT NULL)::int),2) AS pct_graduated,
  round(100.0*avg((b.reached_board)::int),1) AS pct_board,
  round(100.0*avg((b.max_kol > 0)::int),1) AS pct_any_kol,
  round(avg(creator_initial_sol),2) AS avg_dev_buy_sol,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY f.max_holders)::numeric,0) AS med_max_holders
FROM (
  SELECT t.*, x.grp FROM t, LATERAL (VALUES
    ('A ident: ' || CASE WHEN has_tg AND has_tw THEN 'tw+tg' WHEN has_tw THEN 'tw only' WHEN has_tg THEN 'tg only' ELSE 'none' END),
    ('B tw_kind: ' || COALESCE(twitter_kind,'(no twitter)')),
    ('C reuse: ' || CASE WHEN twitter_reuse_count IS NULL THEN '(unknown)' WHEN twitter_reuse_count=0 THEN '0' WHEN twitter_reuse_count=1 THEN '1' WHEN twitter_reuse_count<=5 THEN '2-5' ELSE '>5' END),
    ('D website: ' || has_ws::text)
  ) AS x(grp)
) t LEFT JOIN f ON f.mint=t.mint LEFT JOIN b ON b.mint=t.mint
GROUP BY 1 ORDER BY 1;
