-- R86 — desfechos (lidos só depois do pré-registro 02:56Z, da emenda 03:02Z e da lista congelada 03:04:58Z).
BEGIN READ ONLY;
SET LOCAL statement_timeout='300s';
COPY (
SELECT o.signal_id, o.r_multiple, o.meta->>'r_ex_funding' AS r_ex_funding, o.result::text AS result,
       o.exit_ts, now() AS read_at
FROM signal_outcomes o
JOIN agent_signals s ON s.id = o.signal_id
JOIN strategy_versions sv ON sv.id = s.strategy_version_id
JOIN strategies st ON st.id = sv.strategy_id
WHERE o.tracking_state = 'terminal' AND s.direction::text = 'long'
  AND s.supporting_features->>'cohort' = 'prospective'
  AND (st.key IN ('momentum','volume_anomaly') OR (st.key = 'mean_reversion' AND sv.version = 'v14'))
ORDER BY o.signal_id
) TO STDOUT WITH (FORMAT csv, HEADER);
COMMIT;
