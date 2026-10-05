BEGIN READ ONLY;
SET LOCAL statement_timeout='60s';
SELECT p.features_end_time, p.proposed_at, o.received_at, o.signing_at, o.submitted_at, o.settled_at, o.fill->>'block_time' AS bt, o.fill->>'slot' AS fslot,
  left(p.reasons::text, 900) AS reasons
FROM meme_live_orders o JOIN meme_proposals p ON p.id=o.proposal_id
WHERE o.side='buy' AND o.status='confirmed' ORDER BY o.received_at DESC LIMIT 2;
SELECT column_name FROM information_schema.columns WHERE table_name='meme_decision_tapes' ORDER BY ordinal_position;
COMMIT;
