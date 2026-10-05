BEGIN READ ONLY;
SET LOCAL statement_timeout='60s';
WITH b AS (
  SELECT o.id, (o.fill->>'slot')::bigint AS fslot, p.id AS pid, p.proposed_at, p.mint
  FROM meme_live_orders o JOIN meme_proposals p ON p.id=o.proposal_id
  WHERE o.side='buy' AND o.status='confirmed' AND o.fill ? 'slot'),
t AS (
  SELECT b.id, b.fslot, (SELECT max((e->>'slot')::bigint) FROM jsonb_array_elements(dt.trades) e) AS tslot,
         (SELECT max((e->>'received_at')::timestamptz) FROM jsonb_array_elements(dt.trades) e) AS trecv, b.proposed_at
  FROM b JOIN meme_decision_tapes dt ON dt.mint = b.mint AND dt.as_of BETWEEN b.proposed_at - interval '10 s' AND b.proposed_at + interval '10 s' AND b.pid = ANY(dt.proposal_ids))
SELECT count(*) n,
  percentile_cont(ARRAY[0.1,0.25,0.5,0.75,0.9]) WITHIN GROUP (ORDER BY fslot - tslot) AS slots_trigger_to_fill,
  percentile_cont(ARRAY[0.1,0.5,0.9]) WITHIN GROUP (ORDER BY extract(epoch FROM proposed_at - trecv)) AS lastrecv_to_prop
FROM t WHERE tslot IS NOT NULL;
COMMIT;
