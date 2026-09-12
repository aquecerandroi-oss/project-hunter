-- T3.89 q10 -- recibos de replay dos dois bracos (system_events), para confirmar
-- 12 fatias completas por braco, 0 erros, e ler K4 (unavailable) e a fracao
-- ineligible direto do recibo, sem segundo contador.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset pager off

select data->>'cohort' as coorte,
       count(*) as fatias,
       sum((data->>'bars_evaluated')::bigint) as barras,
       sum(coalesce((data->'evaluations_by_state'->>'unavailable')::bigint,0)) as unavailable,
       sum(coalesce((data->'evaluations_by_state'->>'ineligible')::bigint,0)) as ineligible,
       sum(coalesce((data->'evaluations_by_state'->>'triggered')::bigint,0)) as triggered,
       sum((data->>'errors')::bigint) as erros,
       min(data->>'window_from') as de, max(data->>'window_to') as ate
  from system_events
 where component = 'replay_engine' and event = 'replay_run_finished'
   and data->>'cohort' in ('replay:f2c44f18-5f63-435f-97bb-5f5aaf31cea7',
                            'replay:a94701c9-3459-463e-8922-c1403e91d60a',
                            'replay:a42c888d-0000-0000-0000-000000000000')
 group by 1 order by 1;

-- versoes por decisao, so para checar que nao vazou versao errada nas coortes
select o.meta->>'cohort' as coorte, s.key || ' ' || sv.version as versao,
       count(*) as n, count(distinct mk.symbol) as mercados,
       count(distinct (a.emitted_at at time zone 'UTC')::date) as dias
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  join strategy_versions sv on sv.id = a.strategy_version_id
  join strategies s on s.id = sv.strategy_id
  join markets mk on mk.id = a.market_id
 where o.meta->>'cohort' in ('replay:f2c44f18-5f63-435f-97bb-5f5aaf31cea7',
                              'replay:a94701c9-3459-463e-8922-c1403e91d60a',
                              'replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3')
   and o.tracking_state::text = 'terminal'
 group by 1,2 order by 1,2;

commit;
