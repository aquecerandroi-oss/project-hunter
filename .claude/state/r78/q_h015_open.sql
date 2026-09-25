SET statement_timeout='300s';
SELECT 'paper_open' k, count(*), count(DISTINCT b.mint), min(b.entry_at), max(b.entry_at)
FROM meme_paper_bets b JOIN meme_proposals pr ON pr.id=b.proposal_id
WHERE b.leg='single' AND (b.exit_at IS NULL OR b.pnl_sol IS NULL) AND pr.reasons->0->>'series'='meme_event_gate_v1'
UNION ALL
SELECT 'live_open', count(*), count(DISTINCT p.mint), min(p.entry_at), max(p.entry_at)
FROM meme_live_positions p WHERE p.status <> 'closed';
