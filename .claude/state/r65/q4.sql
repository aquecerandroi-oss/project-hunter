SET statement_timeout='120s';
COPY (
SELECT o.id, o.proposal_id, o.side, o.attempt, o.status, o.reason,
  o.received_at, o.admitted_at, o.simulated_at, o.submitted_at, o.settled_at,
  o.intent::text AS intent, o.fill::text AS fill, o.admission::text AS admission
FROM meme_live_orders o
WHERE o.proposal_id IN (SELECT proposal_id FROM meme_live_positions WHERE status='closed')
ORDER BY o.received_at
) TO STDOUT WITH CSV HEADER;
