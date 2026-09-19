SET statement_timeout='60s';
COPY (
WITH b AS (
  SELECT mint, board, observed_at, mint_updated_at, kol_count, market_cap_usd, holders, txs,
         lag(kol_count) OVER w AS prev_kol, lag(observed_at) OVER w AS prev_obs, lag(mint_updated_at) OVER w AS prev_upd,
         lag(market_cap_usd) OVER w AS prev_mc
  FROM meme_board_observations_2026_09
  WHERE observed_at > now() - interval '72 hours' AND kol_count IS NOT NULL
  WINDOW w AS (PARTITION BY mint ORDER BY observed_at, board)
), inc AS (
  SELECT DISTINCT ON (mint) mint, board, observed_at, mint_updated_at, prev_obs, prev_upd, prev_kol, kol_count, market_cap_usd, prev_mc, holders, txs
  FROM b WHERE prev_kol IS NOT NULL AND kol_count > prev_kol
  ORDER BY mint, observed_at
)
SELECT i.*, t.created_at, t.completed_at, t.migrated_at, (t.twitter IS NOT NULL) AS has_tw, (t.telegram IS NOT NULL) AS has_tg, (t.website IS NOT NULL) AS has_ws, t.twitter_kind, t.twitter_reuse_count
FROM inc i LEFT JOIN meme_tokens t ON t.mint = i.mint
) TO STDOUT WITH (FORMAT csv, HEADER, DELIMITER E'\t');
