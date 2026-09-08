-- T3.40 — recibos: replay_runs, system_events, isolamento da coorte.
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;
select r.cohort, sv.version, r.window_from::date as de, r.window_to::date as ate,
       array_length(r.markets,1) as mkts, r.bars_evaluated, r.signals, r.outcomes_resolved,
       r.outcomes_open, r.seconds, r.workers, r.decision_lag_s, r.evaluations_by_state::text as estados,
       r.errors, r.finished_at
  from replay_runs r join strategy_versions sv on sv.id=r.strategy_version_id
 where r.cohort in ('replay:72cf5671-ec16-4d62-afd6-ace3f7bbf4e1','replay:9a08835a-ae13-4c23-b521-734b2f60a3a2')
 order by r.finished_at;

select level, component, event_type, left(message,110) as mensagem, created_at
  from system_events
 where created_at >= timestamptz '2026-09-08 18:50:00+00'
   and (component in ('activate_strategy_version') or (component='replay_engine' and message like '%momentum v5%') or (component='replay_engine' and message like '%momentum v6%'))
 order by created_at;

-- isolamento
select (select count(*) from shadow_outbox o join agent_signals a on a.id=o.signal_id
          join strategy_versions sv on sv.id=a.strategy_version_id
         where sv.version in ('v5','v6')
           and sv.strategy_id=(select id from strategies where key='momentum')) as outbox_das_variantes,
       (select count(*) from agent_signals a join signal_outcomes o on o.signal_id=a.id
          join strategy_versions sv on sv.id=a.strategy_version_id
         where sv.id in (select id from strategy_versions where version='v5'
                           and strategy_id=(select id from strategies where key='momentum'))) as sinais_v5_total,
       (select count(*) from agent_signals a join signal_outcomes o on o.signal_id=a.id
          join strategy_versions sv on sv.id=a.strategy_version_id
         where sv.id in (select id from strategy_versions where version='v6'
                           and strategy_id=(select id from strategies where key='momentum'))) as sinais_v6_total,
       (select count(*) from agent_signals a join signal_outcomes o on o.signal_id=a.id
          join strategy_versions sv on sv.id=a.strategy_version_id
         where sv.version='v6' and sv.strategy_id=(select id from strategies where key='momentum')
           and o.meta->>'cohort' <> 'replay:9a08835a-ae13-4c23-b521-734b2f60a3a2') as sinais_v6_fora_da_coorte;
commit;
