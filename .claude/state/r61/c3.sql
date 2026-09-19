SET statement_timeout='120s';
COPY (
WITH m AS (
  SELECT mint, max(kol_count) AS max_kol, count(*) AS n
  FROM meme_board_observations_2026_09 WHERE observed_at > now() - interval '72 hours' AND kol_count IS NOT NULL
  GROUP BY mint HAVING max(kol_count) = 0 AND count(*) >= 2
), pool AS (SELECT m.mint FROM m JOIN meme_tokens t ON t.mint=m.mint WHERE t.created_at > now() - interval '72 hours' ORDER BY md5(m.mint) LIMIT 8000)
SELECT o.mint, o.board, o.observed_at, o.mint_updated_at, o.market_cap_usd, o.kol_count, o.holders, o.txs, o.ath_market_cap_usd, o.progress_pct, o.volume_5m_usd
FROM pool p JOIN meme_board_observations_2026_09 o ON o.mint=p.mint AND o.observed_at > now() - interval '72 hours'
) TO STDOUT WITH (FORMAT csv, HEADER, DELIMITER E'\t');
