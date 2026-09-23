SET statement_timeout='900s';
COPY (
SELECT s.id AS signal_id, s.direction::text AS dir,
       o.virtual_entry, o.exit_price, o.entry_ts, o.exit_ts
FROM agent_signals s JOIN signal_outcomes o ON o.signal_id = s.id
WHERE o.tracking_state = 'terminal' AND o.r_multiple IS NOT NULL
  AND s.emitted_at >= TIMESTAMPTZ '2026-09-06 19:00+00'
) TO STDOUT WITH (FORMAT csv, HEADER);
