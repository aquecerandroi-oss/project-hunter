SET statement_timeout='900s';
COPY (
WITH firsts AS (SELECT DISTINCT ON (pop, mint) pop, mint, t0 FROM (
  SELECT 'real' pop, p.mint, pr.proposed_at t0 FROM meme_live_positions p JOIN meme_proposals pr ON pr.id=p.proposal_id WHERE p.status='closed'
  UNION ALL
  SELECT 'paper', b.mint, pr.proposed_at FROM meme_paper_bets b JOIN meme_proposals pr ON pr.id=b.proposal_id
  WHERE b.exit_at IS NOT NULL AND b.pnl_sol IS NOT NULL AND b.leg='single'
    AND pr.reasons->0->>'rule' LIKE 'fluxo\_e\_holders/%' AND pr.proposed_at < now() - interval '10 minutes'
) x ORDER BY pop, mint, t0)
SELECT f.pop, s.mint, s.observed_at, s.source, s.slot, s.virtual_sol_reserves, s.virtual_token_reserves
FROM firsts f JOIN meme_curve_snapshots s ON s.mint = f.mint
WHERE s.observed_at >= f.t0 - interval '3 minutes' AND s.observed_at <= f.t0 + interval '7 minutes' AND s.source='solana_rpc'
ORDER BY f.pop, s.mint, s.observed_at
) TO STDOUT WITH (FORMAT csv, HEADER);
