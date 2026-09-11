-- T3.89 / EXP-0027 passo 1 (b) — o portão lê a linha cujo `end_time` é EXATAMENTE o
-- `source_bar_close`, e a grade de decisão de `mean_reversion v10` é de 15 min: então a
-- previsão de "share de barras elegíveis" tem de ser medida sobre os minutos múltiplos de
-- 15, não sobre todos os minutos. SOMENTE LEITURA, antes de derivar qualquer variante.
\pset pager off
\echo '== (1) share por braço nos fechamentos de 15 min (janela do replay: 2026-06-14..2026-09-10) =='
SELECT count(*)                                                                  AS barras_15m,
       count(*) FILTER (WHERE usable)                                            AS com_linha_usavel,
       round(100.0 * count(*) FILTER (WHERE usable AND value >= 0.10 AND value < 0.60) / count(*), 4) AS braco_a_pct,
       count(*) FILTER (WHERE usable AND value >= 0.10 AND value < 0.60)          AS braco_a_barras,
       round(100.0 * count(*) FILTER (WHERE usable AND value >= 0.60 AND value <= 1.00) / count(*), 4) AS braco_b_pct,
       count(*) FILTER (WHERE usable AND value >= 0.60 AND value <= 1.00)         AS braco_b_barras,
       round(100.0 * count(*) FILTER (WHERE usable AND value < 0.10) / count(*), 4) AS fora_baixo_pct
FROM market_breadth
WHERE breadth_version = 'breadth_v2'
  AND end_time >= '2026-06-14 00:00:00+00' AND end_time < '2026-09-10 00:00:00+00'
  AND extract(minute FROM end_time)::int % 15 = 0;

\echo '== (2) o mesmo por janela de 30 dias (as três da régua) =='
SELECT CASE
         WHEN end_time <  '2026-07-12 00:00:00+00' THEN 'J1 2026-06-14..07-12 (28 d)'
         WHEN end_time <  '2026-08-11 00:00:00+00' THEN 'J2 2026-07-12..08-11 (30 d)'
         ELSE                                            'J3 2026-08-11..09-10 (30 d)'
       END AS janela,
       count(*) AS barras_15m,
       round(100.0 * count(*) FILTER (WHERE usable AND value >= 0.10 AND value < 0.60) / count(*), 4)  AS braco_a_pct,
       round(100.0 * count(*) FILTER (WHERE usable AND value >= 0.60 AND value <= 1.00) / count(*), 4) AS braco_b_pct,
       round(avg(value), 6) AS valor_medio
FROM market_breadth
WHERE breadth_version = 'breadth_v2'
  AND end_time >= '2026-06-14 00:00:00+00' AND end_time < '2026-09-10 00:00:00+00'
  AND extract(minute FROM end_time)::int % 15 = 0
GROUP BY 1 ORDER BY 1;

\echo '== (3) as barras do PAI (coorte replay:c7d138eb) que cada braço teria mantido =='
-- Nota: é a leitura descritiva da faixa sobre as DECISÕES do pai, não a régua.
WITH pai AS (
  SELECT sig.id,
         sig.market_id,
         (sig.supporting_features->>'observation_ts')::timestamptz AS bar_close,
         (so.meta->>'r_ex_funding')::numeric                        AS r_ex_funding
  FROM agent_signals sig
  JOIN signal_outcomes so ON so.signal_id = sig.id
  WHERE sig.supporting_features->>'cohort' = 'replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3'
    AND so.tracking_state = 'terminal'
), com_breadth AS (
  SELECT pai.*, mb.value, mb.usable
  FROM pai
  LEFT JOIN market_breadth mb
         ON mb.breadth_version = 'breadth_v2'
        AND mb.window_minutes = 5
        AND mb.end_time = pai.bar_close
)
SELECT CASE
         WHEN value IS NULL OR NOT usable            THEN 'sem linha usável (fora da série)'
         WHEN value <  0.10                          THEN 'abaixo de 0,10 (sem braço)'
         WHEN value <  0.60                          THEN 'A [0,10; 0,60)'
         ELSE                                             'B [0,60; 1,00]'
       END AS celula,
       count(*)                                     AS n,
       count(DISTINCT (bar_close AT TIME ZONE 'UTC')::date) AS dias,
       round(avg(r_ex_funding), 4)                   AS r_ex_funding_medio,
       round(sum(r_ex_funding), 4)                   AS soma_r
FROM com_breadth
GROUP BY 1 ORDER BY 1;

\echo '== (4) tercis descritivos (t1=0,25 / t2=0,6875, congelados em jun-jul) sobre as decisões do pai de 2026-08-01 em diante =='
WITH pai AS (
  SELECT sig.id,
         (sig.supporting_features->>'observation_ts')::timestamptz AS bar_close,
         (so.meta->>'r_ex_funding')::numeric                        AS r_ex_funding
  FROM agent_signals sig
  JOIN signal_outcomes so ON so.signal_id = sig.id
  WHERE sig.supporting_features->>'cohort' = 'replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3'
    AND so.tracking_state = 'terminal'
)
SELECT CASE
         WHEN mb.value IS NULL OR NOT mb.usable THEN 'sem linha'
         WHEN mb.value <  0.250000              THEN 'T1 baixo  [0; 0,25)'
         WHEN mb.value <  0.687500              THEN 'T2 meio   [0,25; 0,6875)'
         ELSE                                        'T3 alto   [0,6875; 1]'
       END AS tercil,
       count(*)                    AS n,
       round(avg(r_ex_funding), 4) AS r_ex_funding_medio
FROM pai
LEFT JOIN market_breadth mb
       ON mb.breadth_version = 'breadth_v2' AND mb.window_minutes = 5 AND mb.end_time = pai.bar_close
WHERE pai.bar_close >= '2026-08-01 00:00:00+00'
GROUP BY 1 ORDER BY 1;
