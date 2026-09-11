-- T3.89 / EXP-0027 — correção medida ANTES do replay: a faixa do braço B é MEIA-ABERTA no topo
-- (`breadth_policy.py`: min <= valor < max), então `0.60-1.00` é [0,60; 1,00) e o degrau exato
-- 1,0000 (16 de 16 caindo) **não pertence a nenhum braço**. As q01/q02 mediram B com `<= 1.00`;
-- aqui ficam os dois números, lado a lado, e o degrau órfão.
\pset pager off
\echo '== (1) fechamentos de 15 min: B meia-aberta vs B fechada, e o degrau 1,0000 =='
SELECT count(*)                                                            AS barras_15m,
       count(*) FILTER (WHERE usable AND value >= 0.60 AND value < 1.00)    AS b_meia_aberta,
       round(100.0 * count(*) FILTER (WHERE usable AND value >= 0.60 AND value < 1.00) / count(*), 4) AS b_meia_aberta_pct,
       count(*) FILTER (WHERE usable AND value = 1.00)                      AS exatamente_um,
       round(100.0 * count(*) FILTER (WHERE usable AND value = 1.00) / count(*), 4) AS exatamente_um_pct,
       count(*) FILTER (WHERE usable AND (value < 0.10 OR value = 1.00))     AS sem_braco,
       round(100.0 * count(*) FILTER (WHERE usable AND (value < 0.10 OR value = 1.00)) / count(*), 4) AS sem_braco_pct
FROM market_breadth
WHERE breadth_version = 'breadth_v2'
  AND end_time >= '2026-06-14 00:00:00+00' AND end_time < '2026-09-10 00:00:00+00'
  AND extract(minute FROM end_time)::int % 15 = 0;

\echo '== (2) minutos usáveis da série inteira, mesma correção =='
SELECT count(*) AS minutos,
       round(100.0 * count(*) FILTER (WHERE value >= 0.60 AND value < 1.00) / count(*), 4) AS b_meia_aberta_pct,
       round(100.0 * count(*) FILTER (WHERE value = 1.00) / count(*), 4)                   AS exatamente_um_pct
FROM market_breadth
WHERE breadth_version = 'breadth_v2' AND usable;

\echo '== (3) as decisões do PAI por célula, com a faixa B meia-aberta e o degrau órfão à parte =='
WITH pai AS (
  SELECT sig.id, (sig.supporting_features->>'observation_ts')::timestamptz AS bar_close,
         (so.meta->>'r_ex_funding')::numeric AS r_ex_funding
  FROM agent_signals sig JOIN signal_outcomes so ON so.signal_id = sig.id
  WHERE sig.supporting_features->>'cohort' = 'replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3'
    AND so.tracking_state = 'terminal'
)
SELECT CASE
         WHEN mb.value IS NULL OR NOT mb.usable THEN 'sem linha usável'
         WHEN mb.value <  0.10                  THEN '[0; 0,10)  sem braço'
         WHEN mb.value <  0.60                  THEN 'A [0,10; 0,60)'
         WHEN mb.value <  1.00                  THEN 'B [0,60; 1,00)'
         ELSE                                        '= 1,0000  sem braço (órfão)'
       END AS celula,
       count(*) AS n,
       count(DISTINCT (pai.bar_close AT TIME ZONE 'UTC')::date) AS dias,
       round(avg(r_ex_funding), 4) AS r_ex_funding_medio,
       round(sum(r_ex_funding), 4) AS soma_r
FROM pai LEFT JOIN market_breadth mb
       ON mb.breadth_version = 'breadth_v2' AND mb.window_minutes = 5 AND mb.end_time = pai.bar_close
GROUP BY 1 ORDER BY 1;
