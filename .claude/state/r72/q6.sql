SET statement_timeout='300s';
COPY (
WITH first_bet AS (
  SELECT DISTINCT ON (mint) mint, entry_at FROM meme_paper_bets
  WHERE status='closed' AND entry_at >= '2026-09-16' AND exit_at IS NOT NULL AND leg <> 'probe'
  ORDER BY mint, entry_at
)
SELECT s.mint, s.observed_at, s.source, s.slot, s.virtual_sol_reserves, s.virtual_token_reserves, s.real_sol_reserves
FROM meme_curve_snapshots s JOIN first_bet b ON b.mint=s.mint
WHERE s.observed_at >= b.entry_at - interval '2 minutes' AND s.observed_at < b.entry_at + interval '7 minutes'
ORDER BY s.mint, s.observed_at
) TO STDOUT WITH CSV HEADER;
