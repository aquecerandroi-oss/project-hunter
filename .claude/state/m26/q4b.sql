-- q4 corrigida (Astra r2): mints distintos com pelo menos uma observação na curva (graduated_at IS NULL) por board e idade, 25/09
WITH b AS (
  SELECT o.board, o.mint, o.graduated_at, extract(epoch FROM o.observed_at - t.created_at)/60.0 AS age_min
  FROM meme_board_observations o JOIN meme_tokens t ON t.mint = o.mint
  WHERE o.observed_at >= '2026-09-25 00:00+00' AND o.observed_at < '2026-09-26 00:00+00' AND t.created_at IS NOT NULL
)
SELECT board,
  CASE WHEN age_min < 15 THEN 'a <15' WHEN age_min < 30 THEN 'b 15-30' WHEN age_min < 60 THEN 'c 30-60' WHEN age_min < 120 THEN 'd 60-120' ELSE 'e >120' END age,
  count(DISTINCT mint) mints, count(DISTINCT mint) FILTER (WHERE graduated_at IS NULL) mints_on_curve
FROM b WHERE board IN ('movers','graduating') GROUP BY 1,2 ORDER BY 1,2;
SELECT count(DISTINCT o.mint) AS mature_on_curve_any_board
FROM meme_board_observations o JOIN meme_tokens t ON t.mint = o.mint
WHERE o.observed_at >= '2026-09-25' AND o.observed_at < '2026-09-26' AND o.graduated_at IS NULL AND o.board IN ('movers','graduating')
  AND o.observed_at - t.created_at BETWEEN interval '15 minutes' AND interval '120 minutes';
