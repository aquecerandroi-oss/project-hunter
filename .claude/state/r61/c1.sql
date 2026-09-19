SET statement_timeout='120s';
COPY (
WITH m AS (
  SELECT mint, max(kol_count) AS max_kol, count(*) AS n
  FROM meme_board_observations_2026_09 WHERE observed_at > now() - interval '72 hours' AND kol_count IS NOT NULL
  GROUP BY mint HAVING max(kol_count) = 0 AND count(*) >= 2
), pool AS (SELECT m.mint FROM m JOIN meme_tokens t ON t.mint=m.mint WHERE t.created_at > now() - interval '72 hours' ORDER BY md5(m.mint) LIMIT 8000)
SELECT p.mint, t.created_at, t.completed_at, t.migrated_at, (t.twitter IS NOT NULL) AS has_tw, (t.telegram IS NOT NULL) AS has_tg, (t.website IS NOT NULL) AS has_ws, t.twitter_kind, t.twitter_reuse_count
FROM pool p JOIN meme_tokens t ON t.mint=p.mint
) TO STDOUT WITH (FORMAT csv, HEADER, DELIMITER E'\t');
