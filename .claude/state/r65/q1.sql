SET statement_timeout='60s';
\echo == sample decision ==
SELECT jsonb_pretty(pr.decision) FROM meme_live_positions p JOIN meme_proposals pr ON pr.id=p.proposal_id WHERE p.status='closed' ORDER BY p.entry_at DESC LIMIT 1;
\echo == sample admission (buy) ==
SELECT jsonb_pretty(o.admission) FROM meme_live_positions p JOIN meme_live_orders o ON o.id=p.entry_order_id WHERE p.status='closed' ORDER BY p.entry_at DESC LIMIT 1;
