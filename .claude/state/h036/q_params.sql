BEGIN READ ONLY;
SELECT sv.version, sv.code_ref, sv.default_parameters::text, sv.eligibility_policy::text, left(sv.changelog, 600)
FROM strategy_versions sv JOIN strategies st ON st.id = sv.strategy_id
WHERE st.key = 'mean_reversion' AND sv.version IN ('v6','v14');
COMMIT;
