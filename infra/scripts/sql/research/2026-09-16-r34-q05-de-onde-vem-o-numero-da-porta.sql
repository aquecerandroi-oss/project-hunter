-- R34 q05 — de onde vem o numero que a porta le: tape_source / tape_reason em meme_features_1m.
\set d0 '2026-09-15 03:00+00'
\set d1 '2026-09-16 03:00+00'
SET statement_timeout = 60000;
SELECT coalesce(tape_source, concat('(nulo) ', coalesce(tape_reason, 'sem motivo'))) AS fonte,
       count(*) AS linhas,
       count(DISTINCT mint) AS moedas,
       round(100.0 * count(*) OVER () / count(*) OVER (), 1) AS x,
       count(*) FILTER (WHERE unique_buyers IS NOT NULL) AS com_unique_buyers,
       count(*) FILTER (WHERE net_sol_flow_1m IS NOT NULL) AS com_net_flow,
       count(*) FILTER (WHERE creator_sold IS NOT NULL) AS com_creator_sold,
       count(*) FILTER (WHERE curve_volume_1m_sol IS NOT NULL) AS com_volume
FROM meme_features_1m
WHERE end_time >= timestamptz :'d0' AND end_time < timestamptz :'d1'
GROUP BY 1 ORDER BY 2 DESC;

-- (b) o mesmo na serie de 15 s, que e a que KB-0099/0102/0108/0112/0114 leram.
SELECT coalesce(tape_source, concat('(nulo) ', coalesce(tape_reason, 'sem motivo'))) AS fonte,
       count(*) AS linhas, count(DISTINCT mint) AS moedas,
       count(*) FILTER (WHERE unique_buyers_60s IS NOT NULL) AS com_unique_buyers_60s,
       count(*) FILTER (WHERE net_sol_flow_60s IS NOT NULL) AS com_net_flow_60s
FROM meme_features_15s
WHERE as_of >= timestamptz :'d0' AND as_of < timestamptz :'d1'
GROUP BY 1 ORDER BY 2 DESC;
