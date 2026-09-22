SET statement_timeout='300s';
COPY (
WITH pos AS (SELECT mint, min(entry_at) AS t0, max(exit_at) AS t1 FROM meme_live_positions WHERE status='closed' GROUP BY mint)
SELECT s.mint, s.observed_at, s.received_at, s.source, s.slot, s.virtual_sol_reserves, s.virtual_token_reserves, s.real_sol_reserves, s.complete
FROM meme_curve_snapshots s JOIN pos ON pos.mint=s.mint
WHERE s.observed_at >= pos.t0 - interval '2 minutes' AND s.observed_at < pos.t1 + interval '10 minutes'
ORDER BY s.mint, s.observed_at
) TO STDOUT WITH CSV HEADER;
