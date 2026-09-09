-- T3.47b q13 — recibos (replay_runs, system_events da janela), isolamento da coorte
-- (shadow_outbox), roster DEPOIS das tres aposentadorias e da nova v8, e o estado dos
-- acompanhamentos que ficaram abertos nas versoes aposentadas. Somente leitura.
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;

-- 1. recibos dos dois replays desta tarefa
select left(r.cohort,24) as coorte, s.key||' '||sv.version as versao,
       to_char(r.window_from,'MM-DD') as de, to_char(r.window_to,'MM-DD') as ate,
       array_length(r.markets,1) as mkts, r.bars_evaluated as bars, r.signals as sig,
       r.outcomes_resolved as out, r.outcomes_open as aberto, r.seconds as seg,
       r.workers as wk, r.decision_lag_s as lag, r.evaluations_by_state as estados, r.errors as err
  from replay_runs r join strategy_versions sv on sv.id=r.strategy_version_id
  join strategies s on s.id=sv.strategy_id
 where r.cohort = 'replay:8ac79cca-916b-4f7f-bd83-01b068b9f811'
 order by r.started_at;

-- 2. system_events da janela desta tarefa (a partir de 23:30Z)
select level, component, event, left(message, 118) as mensagem, created_at
  from system_events
 where created_at >= timestamptz '2026-09-08 23:30:00+00'
   and component in ('activate_strategy_version','replay_engine')
 order by created_at;

-- 3. isolamento: a coorte de replay nao publica
select (select count(*) from shadow_outbox where payload::text like '%8ac79cca-916b-4f7f-bd83-01b068b9f811%') as outbox_da_coorte,
       (select count(*) from shadow_outbox where dispatched_at is null) as outbox_pendente_total,
       (select count(*) from shadow_outbox) as outbox_total;

-- 4. por coorte, a nova versao: replay x prospectiva
select s.key||' '||sv.version as versao, a.supporting_features->>'cohort' as coorte,
       count(*) as sinais, max(a.emitted_at) as ultimo
  from agent_signals a join strategy_versions sv on sv.id=a.strategy_version_id
  join strategies s on s.id=sv.strategy_id
 where s.key='mean_reversion' and sv.version='v8'
 group by 1,2 order by 2;

-- 5. roster DEPOIS
select s.key||' '||sv.version as versao, sv.status, sv.purpose,
       to_char(sv.deprecated_at,'HH24:MI:SS') as aposentada_utc,
       substring(sv.changelog from 'params_hash=([0-9a-f]{12})') as params_hash
  from strategy_versions sv join strategies s on s.id=sv.strategy_id
 where sv.status in ('active','deprecated')
 order by sv.status, s.key, (regexp_replace(sv.version,'\D','','g'))::int;

-- 6. quantas versoes ativas agora
select status, count(*) as versoes from strategy_versions group by 1 order by 1;

-- 7. o custo declarado da aposentadoria: os acompanhamentos que ficaram abertos
select s.key||' '||sv.version as versao, sv.status, m.symbol,
       o.tracking_state::text as estado, coalesce(o.result::text,'-') as resultado,
       to_char(o.tracked_until,'YYYY-MM-DD HH24:MI:SS') as acompanhado_ate,
       to_char(a.expires_at,'YYYY-MM-DD HH24:MI:SS') as expira_em,
       to_char(o.updated_at,'YYYY-MM-DD HH24:MI:SS') as atualizado_em
  from shadow_episodes e
  join strategy_versions sv on sv.id=e.strategy_version_id
  join strategies s on s.id=sv.strategy_id
  join markets m on m.id=e.market_id
  left join signal_outcomes o on o.signal_id=e.open_outcome_signal_id
  left join agent_signals a on a.id=e.open_outcome_signal_id
 where (s.key,sv.version) in (('momentum','v7'),('mean_reversion','v4'),('mean_reversion','v5'))
   and e.open_outcome_signal_id is not null
 order by 1, m.symbol;
commit;

-- 8. (acrescentado apos a primeira corrida) linhagem e conteudo proprio da v8
begin transaction isolation level repeatable read read only;
\pset border 2
select s.key||' '||sv.version as versao, sv.status, sv.purpose,
       sv.default_parameters->>'atr_pct_min' as piso,
       sv.default_parameters->>'stop_atr' as stop_atr,
       sv.default_parameters->>'target_atr' as target_atr,
       sv.default_parameters->>'target2_atr' as target2_atr,
       sv.code_ref = pai.code_ref as code_ref_igual_ao_pai,
       right(sv.code_ref,16) as sufixo,
       sv.changelog
  from strategy_versions sv join strategies s on s.id=sv.strategy_id
  join strategy_versions pai on pai.strategy_id=sv.strategy_id
   and pai.version = substring(sv.changelog from 'derived_from=(v[0-9]+)')
 where s.key='mean_reversion' and sv.version='v8';
commit;

-- 9. (acrescentado apos a segunda corrida) o primeiro e o ultimo sinal prospectivo da v8
begin transaction isolation level repeatable read read only;
\pset border 2
select min(a.emitted_at) as primeiro, max(a.emitted_at) as ultimo, count(*) as n
  from agent_signals a join strategy_versions sv on sv.id=a.strategy_version_id
  join strategies s on s.id=sv.strategy_id
 where s.key='mean_reversion' and sv.version='v8' and a.supporting_features->>'cohort'='prospective';
commit;
