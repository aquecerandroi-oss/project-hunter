-- primeira decisão por (população, mint), mesma regra do q_pop; janela [t0-3 min, t0+7 min]
SET statement_timeout='900s';
COPY (
WITH firsts AS (SELECT DISTINCT ON (pop, mint) pop, mint, t0 FROM (
  SELECT 'real' pop, p.mint, pr.proposed_at t0 FROM meme_live_positions p JOIN meme_proposals pr ON pr.id=p.proposal_id WHERE p.status='closed'
  UNION ALL
  SELECT 'paper', b.mint, pr.proposed_at FROM meme_paper_bets b JOIN meme_proposals pr ON pr.id=b.proposal_id
  WHERE b.exit_at IS NOT NULL AND b.pnl_sol IS NOT NULL AND b.leg='single'
    AND pr.reasons->0->>'rule' LIKE 'fluxo\_e\_holders/%' AND pr.proposed_at < now() - interval '10 minutes'
) x ORDER BY pop, mint, t0)
SELECT f.pop, t.mint, t.block_time, t.received_at, t.slot, t.signature, t.event_index, t.trader, t.side, t.sol_lamports,
       round(t.token_amount * power(10, COALESCE(t.token_decimals, 6)))::bigint AS token_raw
FROM firsts f JOIN meme_trades t ON t.mint = f.mint
WHERE t.block_time >= f.t0 - interval '3 minutes' AND t.block_time <= f.t0 + interval '7 minutes'
ORDER BY f.pop, t.mint, t.slot, t.signature, t.event_index
) TO STDOUT WITH (FORMAT csv, HEADER);
