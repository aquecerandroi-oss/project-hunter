SET statement_timeout='120s';
COPY (
WITH b AS (
  SELECT mint, kol_count, lag(kol_count) OVER (PARTITION BY mint ORDER BY observed_at, board) AS prev_kol
  FROM meme_board_observations_2026_09
  WHERE observed_at > now() - interval '72 hours' AND kol_count IS NOT NULL
), inc AS (SELECT DISTINCT mint FROM b WHERE prev_kol IS NOT NULL AND kol_count > prev_kol)
SELECT o.mint, o.board, o.observed_at, o.mint_updated_at, o.market_cap_usd, o.kol_count, o.holders, o.txs, o.ath_market_cap_usd, o.progress_pct, o.volume_5m_usd
FROM inc i JOIN meme_board_observations_2026_09 o ON o.mint=i.mint AND o.observed_at > now() - interval '72 hours'
) TO STDOUT WITH (FORMAT csv, HEADER, DELIMITER E'\t');
