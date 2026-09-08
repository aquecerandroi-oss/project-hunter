-- T3.47 q14 — recibos das 12 corridas, eventos da janela, isolamento das coortes,
-- conteudo/linhagem das seis versoes novas, cobertura e a checagem C5 da banda paper_v1.
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;

-- 1. recibos
select left(r.cohort,15) as coorte, sv.version as ver,
       r.window_from::date as de, r.window_to::date as ate, cardinality(r.markets) as mkts,
       r.bars_evaluated as bars, r.signals as sig, r.outcomes_resolved as out,
       r.outcomes_open as aberto, round(r.seconds::numeric,3) as seg, r.workers as wk,
       r.decision_lag_s as lag, r.evaluations_by_state::text as estados, r.errors as err
  from replay_runs r join strategy_versions sv on sv.id = r.strategy_version_id
 where r.cohort in ('replay:293d98b7-90e1-4dfe-a604-60556f3b175e','replay:ee11d60b-3a4e-48be-94a3-1aecb8cf16fd',
                    'replay:af24ee08-01cf-41ba-9b7a-1b43172bea28','replay:66fa85cb-1d51-4330-a00b-00964b430ab4',
                    'replay:9d99748b-21b9-44a7-8980-32c37b931e6e','replay:264b227f-5bc0-4930-8c5b-2e883c0a858e')
 order by sv.version, r.window_from;

-- 2. eventos da janela
select level, component, event, left(message, 96) as mensagem, created_at
  from system_events
 where created_at >= timestamptz '2026-09-08 22:27:00+00'
   and component in ('activate_strategy_version','replay_engine')
 order by created_at;

-- 3. isolamento: shadow_outbox das coortes de replay e sinais fora delas
select (select count(*) from shadow_outbox o
         where o.payload->>'cohort' in ('replay:293d98b7-90e1-4dfe-a604-60556f3b175e',
           'replay:ee11d60b-3a4e-48be-94a3-1aecb8cf16fd','replay:af24ee08-01cf-41ba-9b7a-1b43172bea28',
           'replay:66fa85cb-1d51-4330-a00b-00964b430ab4','replay:9d99748b-21b9-44a7-8980-32c37b931e6e',
           'replay:264b227f-5bc0-4930-8c5b-2e883c0a858e')) as outbox_das_coortes,
       (select count(*) from shadow_outbox) as outbox_total;

select s.key||' '||sv.version as versao,
       case when a.meta->>'cohort' like 'replay:%' then 'replay' else coalesce(a.meta->>'cohort','?') end as coorte,
       count(*) as sinais, min(a.emitted_at) as primeiro
  from agent_signals a
  join strategy_versions sv on sv.id=a.strategy_version_id
  join strategies s on s.id=sv.strategy_id
 where (s.key,sv.version) in (('momentum','v7'),('momentum','v8'),('mean_reversion','v4'),
                              ('mean_reversion','v5'),('mean_reversion','v6'),('mean_reversion','v7'))
 group by 1,2 order by 1,2;

-- 4. conteudo proprio e linhagem
select s.key||' '||sv.version as versao, sv.status, sv.purpose,
       sv.default_parameters->>'atr_pct_min' as atr_pct_min,
       sv.default_parameters->>'stop_atr' as stop_atr,
       sv.default_parameters->>'target_atr' as target_atr,
       sv.default_parameters->>'target2_atr' as target2_atr,
       sv.default_parameters->>'target3_atr' as target3_atr,
       (sv.code_ref = (select code_ref from strategy_versions p where p.strategy_id=sv.strategy_id and p.version='v1')) as code_ref_igual_ao_v1,
       sv.changelog
  from strategy_versions sv join strategies s on s.id=sv.strategy_id
 where (s.key,sv.version) in (('momentum','v7'),('momentum','v8'),('mean_reversion','v4'),
                              ('mean_reversion','v5'),('mean_reversion','v6'),('mean_reversion','v7'))
 order by 1;
commit;
