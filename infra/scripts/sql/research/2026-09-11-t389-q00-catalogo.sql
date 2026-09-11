-- T3.89 / EXP-0027 — catálogo somente leitura ANTES de derivar qualquer coisa.
-- (1) as versões de mean_reversion (pai v10, purpose, política, code_ref);
-- (2) a coorte do pai (replay:c7d138eb-…): n, dias, eixo r_ex_funding;
-- (3) a grade de decisão congelada de v10 (para dimensionar as fatias do replay).
\pset pager off
\echo '== (1) mean_reversion: versões =='
SELECT sv.version,
       sv.status,
       sv.purpose,
       sv.id,
       sv.eligibility_policy,
       left(sv.code_ref, 24) AS code_ref,
       sv.activated_at,
       sv.deprecated_at
FROM strategy_versions sv
JOIN strategies s ON s.id = sv.strategy_id
WHERE s.key = 'mean_reversion'
ORDER BY sv.created_at;

\echo '== (2) parâmetros congelados de mean_reversion v10 =='
SELECT jsonb_pretty(sv.default_parameters) AS default_parameters
FROM strategy_versions sv
JOIN strategies s ON s.id = sv.strategy_id
WHERE s.key = 'mean_reversion' AND sv.version = 'v10';

\echo '== (3) a coorte do pai: decisões, dias, mercados =='
SELECT count(*)                                   AS decisoes,
       count(DISTINCT date_trunc('day', sig.emitted_at)) AS dias_emissao,
       count(DISTINCT sig.market_id)              AS mercados,
       min(sig.supporting_features->>'observation_ts') AS primeira_barra,
       max(sig.supporting_features->>'observation_ts') AS ultima_barra
FROM agent_signals sig
WHERE sig.supporting_features->>'cohort' = 'replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3';

\echo '== (4) desfechos terminais do pai e cobertura de eixo =='
SELECT so.tracking_state,
       count(*)                                             AS n,
       count(so.r_multiple)                                 AS com_r_net,
       count(so.meta->'r_ex_funding')                        AS com_r_ex_funding
FROM signal_outcomes so
JOIN agent_signals sig ON sig.id = so.signal_id
WHERE sig.supporting_features->>'cohort' = 'replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3'
GROUP BY so.tracking_state
ORDER BY so.tracking_state;
