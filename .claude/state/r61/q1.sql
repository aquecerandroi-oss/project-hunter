SET statement_timeout='60s';
-- per mint: first obs, first obs with kol>=1, whether a kol=0 obs preceded it
WITH b AS (
  SELECT mint, board, observed_at, mint_updated_at, kol_count, market_cap_usd, age_s
  FROM meme_board_observations_2026_09
  WHERE observed_at > now() - interval '72 hours' AND kol_count IS NOT NULL
), m AS (
  SELECT mint,
         min(observed_at) AS first_obs,
         min(observed_at) FILTER (WHERE kol_count >= 1) AS first_kol_obs,
         min(observed_at) FILTER (WHERE kol_count = 0) AS first_zero_obs,
         max(kol_count) AS max_kol,
         count(*) AS n_rows, count(DISTINCT board) AS n_boards
  FROM b GROUP BY mint
)
SELECT
  count(*) AS mints,
  count(*) FILTER (WHERE max_kol >= 1) AS with_kol,
  count(*) FILTER (WHERE first_kol_obs IS NOT NULL AND first_zero_obs IS NOT NULL AND first_zero_obs < first_kol_obs) AS witnessed_0_to_1,
  count(*) FILTER (WHERE first_kol_obs IS NOT NULL AND first_kol_obs = first_obs) AS born_with_kol,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY n_rows) AS med_rows
FROM m;
SELECT kol_count, count(*) FROM meme_board_observations_2026_09 WHERE observed_at > now() - interval '72 hours' AND board='new' GROUP BY 1 ORDER BY 1 LIMIT 12;
SELECT source, count(*), count(DISTINCT mint) FROM meme_curve_snapshots_2026_09 WHERE observed_at > now() - interval '72 hours' GROUP BY 1;
SELECT snapshot_source, count(*) FROM meme_features_15s_2026_09 WHERE as_of > now() - interval '72 hours' GROUP BY 1;
