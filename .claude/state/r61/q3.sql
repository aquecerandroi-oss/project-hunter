SET statement_timeout='60s';
WITH b AS (
  SELECT mint, board, observed_at, mint_updated_at, kol_count, market_cap_usd, age_s, holders, txs,
         lag(kol_count) OVER w AS prev_kol, lag(observed_at) OVER w AS prev_obs, lag(mint_updated_at) OVER w AS prev_upd
  FROM meme_board_observations_2026_09
  WHERE observed_at > now() - interval '72 hours' AND kol_count IS NOT NULL
  WINDOW w AS (PARTITION BY mint ORDER BY observed_at, board)
), inc AS (
  SELECT DISTINCT ON (mint) *
  FROM b WHERE prev_kol IS NOT NULL AND kol_count > prev_kol
  ORDER BY mint, observed_at
)
SELECT prev_kol, count(*), percentile_cont(0.5) WITHIN GROUP (ORDER BY age_s) med_age,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM observed_at - prev_obs)) med_gap_s,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY market_cap_usd) med_mc
FROM inc GROUP BY 1 ORDER BY 1 LIMIT 8;
-- snapshot coverage for those mints around the event
WITH b AS (
  SELECT mint, board, observed_at, mint_updated_at, kol_count, market_cap_usd, age_s,
         lag(kol_count) OVER w AS prev_kol, lag(observed_at) OVER w AS prev_obs
  FROM meme_board_observations_2026_09
  WHERE observed_at > now() - interval '72 hours' AND kol_count IS NOT NULL
  WINDOW w AS (PARTITION BY mint ORDER BY observed_at, board)
), inc AS (
  SELECT DISTINCT ON (mint) mint, mint_updated_at AS t_kol, prev_kol FROM b WHERE prev_kol IS NOT NULL AND kol_count > prev_kol ORDER BY mint, observed_at
), cov AS (
  SELECT i.mint, i.prev_kol,
    count(s.*) FILTER (WHERE s.observed_at BETWEEN i.t_kol - interval '5 min' AND i.t_kol) AS before5,
    count(s.*) FILTER (WHERE s.observed_at BETWEEN i.t_kol AND i.t_kol + interval '15 min') AS after15
  FROM inc i LEFT JOIN meme_curve_snapshots_2026_09 s ON s.mint = i.mint AND s.observed_at BETWEEN i.t_kol - interval '5 min' AND i.t_kol + interval '15 min'
  GROUP BY 1,2
)
SELECT prev_kol=0 AS zero_to_one, count(*), count(*) FILTER (WHERE after15 >= 10) AS ge10_after, count(*) FILTER (WHERE before5 >= 3) AS ge3_before,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY after15) med_after, percentile_cont(0.5) WITHIN GROUP (ORDER BY before5) med_before
FROM cov GROUP BY 1;
