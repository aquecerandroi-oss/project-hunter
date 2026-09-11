-- T3.89 / EXP-0027 passo 2 — o que a via auditada gravou: ids, digests, política e linhagem.
\pset pager off
SELECT sv.version, sv.id, sv.status, sv.purpose,
       sv.eligibility_policy,
       sv.code_ref,
       sv.activated_at,
       sv.changelog
FROM strategy_versions sv JOIN strategies s ON s.id = sv.strategy_id
WHERE s.key = 'mean_reversion' AND sv.version IN ('v10', 'v18', 'v19')
ORDER BY sv.version;
