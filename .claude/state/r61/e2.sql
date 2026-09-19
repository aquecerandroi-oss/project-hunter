SET statement_timeout='120s';
COPY (
WITH b AS (
  SELECT mint, kol_count, lag(kol_count) OVER (PARTITION BY mint ORDER BY observed_at, board) AS prev_kol
  FROM meme_board_observations_2026_09
  WHERE observed_at > now() - interval '72 hours' AND kol_count IS NOT NULL
), inc AS (SELECT DISTINCT mint FROM b WHERE prev_kol IS NOT NULL AND kol_count > prev_kol)
SELECT s.mint, s.observed_at, s.source, s.mcap_sol, s.real_sol_reserves, s.complete
FROM inc i JOIN meme_tokens t ON t.mint=i.mint
JOIN meme_curve_snapshots_2026_09 s ON s.mint=i.mint AND s.observed_at BETWEEN t.created_at AND t.created_at + interval '60 min'
) TO STDOUT WITH (FORMAT csv, HEADER, DELIMITER E'\t');
