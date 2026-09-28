-- R83 — desfechos (lidos só depois do desenho congelado em notes-R83.md §2 e da revisão da Astra).
SET statement_timeout='600s';
COPY (
SELECT o.signal_id, o.r_multiple, o.meta->>'r_ex_funding' AS r_ex_funding, o.result::text AS result, o.exit_ts
FROM signal_outcomes o
JOIN agent_signals s ON s.id = o.signal_id
WHERE o.tracking_state = 'terminal' AND s.direction::text = 'long'
ORDER BY o.signal_id
) TO STDOUT WITH (FORMAT csv, HEADER);
