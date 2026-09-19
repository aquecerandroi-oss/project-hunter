SET statement_timeout='120s';
COPY (
WITH mm AS (SELECT DISTINCT x.mint FROM meme_event_matches x WHERE x.matched_at > now() - interval '72 hours')
SELECT s.mint, s.observed_at, s.source, s.mcap_sol, s.real_sol_reserves, s.complete
FROM mm JOIN meme_tokens t ON t.mint=mm.mint JOIN meme_curve_snapshots_2026_09 s ON s.mint=mm.mint AND s.observed_at BETWEEN t.created_at AND t.created_at + interval '60 min'
) TO STDOUT WITH (FORMAT csv, HEADER, DELIMITER E'\t');
