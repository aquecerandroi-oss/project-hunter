-- T3.91 / EXP-0029 passo 1 (c) — leitura DESCRITIVA por célula sobre as decisões do PAI
-- (`mean_reversion v10`, coorte replay:c7d138eb…, 798 terminais), juntando cada decisão à linha
-- de `dispersion_24h_v1` do seu `source_bar_close`. NÃO é o resultado do experimento e não move a
-- régua (a população dos braços difere pela divergência de máquina de estados do slot,
-- PIPELINE §4b item 11). Tercis: `t1`/`t2` vêm do q01 (5) e entram aqui como literais depois da
-- leitura — preenchidos abaixo com os valores medidos. SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset pager off
\echo '== (1) as decisões do pai por célula da dispersão (todas as 798) =='
WITH pai AS (
  SELECT sig.id,
         sig.market_id,
         (sig.supporting_features->>'observation_ts')::timestamptz AS bar_close,
         (so.meta->>'r_ex_funding')::numeric                        AS r_ex_funding
  FROM agent_signals sig
  JOIN signal_outcomes so ON so.signal_id = sig.id
  WHERE sig.supporting_features->>'cohort' = 'replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3'
    AND so.tracking_state = 'terminal'
    AND so.meta->>'r_ex_funding' IS NOT NULL
), com_disp AS (
  SELECT pai.*, md.dispersion, md.usable
  FROM pai
  LEFT JOIN market_dispersion md
         ON md.dispersion_version = 'dispersion_24h_v1'
        AND md.end_time = pai.bar_close
)
SELECT CASE
         WHEN dispersion IS NULL OR NOT usable          THEN '6 sem linha usável'
         WHEN dispersion <  -0.10                       THEN '4 < -0,10 (sem braço)'
         WHEN dispersion <  -0.03                       THEN '1 A [-0,10; -0,03)'
         WHEN dispersion <   0.00                       THEN '3 [-0,03; 0,00) (sem braço)'
         WHEN dispersion <   0.10                       THEN '2 B [0,00; 0,10)'
         ELSE                                                '5 >= 0,10 (sem braço)'
       END AS celula,
       count(*)                                              AS n,
       count(DISTINCT (bar_close AT TIME ZONE 'UTC')::date)  AS dias,
       round(avg(r_ex_funding), 4)                           AS r_ex_funding_medio,
       round(sum(r_ex_funding), 4)                           AS soma_r,
       min(bar_close) AS de, max(bar_close) AS ate
FROM com_disp
GROUP BY 1 ORDER BY 1;

\echo '== (1b) o mesmo, só as decisões de 2026-06-16 em diante (o pai cortado no início da série) =='
WITH pai AS (
  SELECT sig.id,
         (sig.supporting_features->>'observation_ts')::timestamptz AS bar_close,
         (so.meta->>'r_ex_funding')::numeric                        AS r_ex_funding
  FROM agent_signals sig
  JOIN signal_outcomes so ON so.signal_id = sig.id
  WHERE sig.supporting_features->>'cohort' = 'replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3'
    AND so.tracking_state = 'terminal'
    AND so.meta->>'r_ex_funding' IS NOT NULL
    AND sig.emitted_at >= '2026-06-16 00:00:00+00'
)
SELECT count(*) AS n_pai_cortado,
       count(DISTINCT (bar_close AT TIME ZONE 'UTC')::date) AS dias,
       round(avg(r_ex_funding), 4) AS r_ex_funding_medio,
       round(sum(r_ex_funding), 4) AS soma_r,
       min(bar_close) AS de, max(bar_close) AS ate
FROM pai;

\echo '== (2) tercis congelados (t1/t2 do q01 (5)) sobre as decisões do pai de 2026-08-01 em diante =='
WITH pai AS (
  SELECT sig.id,
         (sig.supporting_features->>'observation_ts')::timestamptz AS bar_close,
         (so.meta->>'r_ex_funding')::numeric                        AS r_ex_funding
  FROM agent_signals sig
  JOIN signal_outcomes so ON so.signal_id = sig.id
  WHERE sig.supporting_features->>'cohort' = 'replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3'
    AND so.tracking_state = 'terminal'
    AND so.meta->>'r_ex_funding' IS NOT NULL
)
SELECT CASE
         WHEN md.dispersion IS NULL OR NOT md.usable THEN 'sem linha'
         WHEN md.dispersion <  :'t1'::numeric        THEN 'T1 baixo  [-1; t1)'
         WHEN md.dispersion <  :'t2'::numeric        THEN 'T2 meio   [t1; t2)'
         ELSE                                             'T3 alto   [t2; +1]'
       END AS tercil,
       count(*)                    AS n,
       count(DISTINCT (bar_close AT TIME ZONE 'UTC')::date) AS dias,
       round(avg(r_ex_funding), 4) AS r_ex_funding_medio,
       round(sum(r_ex_funding), 4) AS soma_r
FROM pai
LEFT JOIN market_dispersion md
       ON md.dispersion_version = 'dispersion_24h_v1' AND md.end_time = pai.bar_close
WHERE pai.bar_close >= '2026-08-01 00:00:00+00'
GROUP BY 1 ORDER BY 1;

\echo '== (3) K4 do pai (unavailable no recibo do replay original, 90 d) =='
SELECT data->>'cohort' AS coorte,
       count(*) AS fatias,
       sum((data->>'bars_evaluated')::bigint) AS barras,
       sum(coalesce((data->'evaluations_by_state'->>'unavailable')::bigint,0)) AS unavailable,
       round(100.0 * sum(coalesce((data->'evaluations_by_state'->>'unavailable')::bigint,0))
             / sum((data->>'bars_evaluated')::bigint), 4) AS k4_pct
FROM system_events
WHERE component = 'replay_engine' AND event = 'replay_run_finished'
  AND data->>'cohort' = 'replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3'
GROUP BY 1;

commit;
