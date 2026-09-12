-- T3.89 q12 -- K4 (unavailable) do PAI, lido do recibo do replay original
-- (EXP-0025, coorte replay:c7d138eb-...), na mesma janela do braco (90 d,
-- 2026-06-12 -> 2026-09-10; breadth_v2 comeca 2 dias depois, 2026-06-14, o
-- efeito de 2 dias em 90 no denominador de K4 e desprezavel e fica declarado).
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '120s';
\pset pager off

select data->>'cohort' as coorte,
       count(*) as fatias,
       sum((data->>'bars_evaluated')::bigint) as barras,
       sum(coalesce((data->'evaluations_by_state'->>'unavailable')::bigint,0)) as unavailable,
       round(100.0 * sum(coalesce((data->'evaluations_by_state'->>'unavailable')::bigint,0))
             / sum((data->>'bars_evaluated')::bigint), 4) as k4_pct
  from system_events
 where component = 'replay_engine' and event = 'replay_run_finished'
   and data->>'cohort' = 'replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3'
 group by 1;

commit;
