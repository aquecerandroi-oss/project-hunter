SET statement_timeout='120s';
COPY (
WITH m AS (
  SELECT mint, max(kol_count) AS max_kol, count(*) AS n
  FROM meme_board_observations_2026_09 WHERE observed_at > now() - interval '72 hours' AND kol_count IS NOT NULL
  GROUP BY mint HAVING max(kol_count) = 0 AND count(*) >= 2
), pool AS (SELECT m.mint FROM m JOIN meme_tokens t ON t.mint=m.mint WHERE t.created_at > now() - interval '72 hours' ORDER BY md5(m.mint) LIMIT 8000)
SELECT s.mint, s.observed_at, s.source, s.mcap_sol, s.real_sol_reserves, s.complete
FROM pool p JOIN meme_tokens t ON t.mint=p.mint
JOIN meme_curve_snapshots_2026_09 s ON s.mint=p.mint AND s.observed_at BETWEEN t.created_at AND t.created_at + interval '60 min'
) TO STDOUT WITH (FORMAT csv, HEADER, DELIMITER E'\t');
