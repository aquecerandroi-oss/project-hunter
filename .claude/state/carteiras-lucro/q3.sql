BEGIN READ ONLY;
SET LOCAL statement_timeout='60s';
SELECT left(t.trades::text, 400) AS trades_head, jsonb_typeof(t.trades) FROM meme_decision_tapes t ORDER BY as_of DESC LIMIT 1;
\echo '== proposta -> confirmado (settled) e bloco - proposta, compras reais desde 18/09 18Z'
SELECT count(*) n,
 percentile_cont(ARRAY[0.1,0.5,0.9]) WITHIN GROUP (ORDER BY extract(epoch FROM o.settled_at - p.proposed_at)) AS prop_to_settled,
 percentile_cont(ARRAY[0.1,0.5,0.9]) WITHIN GROUP (ORDER BY extract(epoch FROM (o.fill->>'block_time')::timestamptz - p.proposed_at)) AS prop_to_blocktime
FROM meme_live_orders o JOIN meme_proposals p ON p.id=o.proposal_id
WHERE o.side='buy' AND o.status='confirmed' AND o.fill ? 'block_time' AND o.received_at >= '2026-09-18 18:00Z'
  AND p.reasons->0->>'series' = 'meme_event_gate_v1';
COMMIT;
