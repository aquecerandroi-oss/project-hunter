SET statement_timeout='300s';
WITH live AS (
  SELECT p.mint, pr.decided_at
  FROM meme_live_positions p JOIN meme_proposals pr ON pr.id = p.proposal_id
),
paper AS (
  SELECT b.mint, pr.decided_at
  FROM meme_paper_bets b JOIN meme_proposals pr ON pr.id = b.proposal_id
  WHERE b.exit_at IS NOT NULL AND b.pnl_sol IS NOT NULL
)
SELECT 'live_trades_to_decision', count(*)::text
FROM live l JOIN meme_trades t ON t.mint = l.mint AND t.block_time <= l.decided_at + interval '10 s';
SELECT 'n_live_mints', count(DISTINCT mint)::text FROM meme_live_positions;
SELECT 'n_paper_mints', count(DISTINCT mint)::text FROM meme_paper_bets WHERE exit_at IS NOT NULL AND pnl_sol IS NOT NULL;
