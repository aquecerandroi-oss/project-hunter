-- T3.42 q16 — recibos: replay_runs das tres coortes e system_events da janela.
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;
select left(r.cohort,16)||'…' as coorte, sv.version as ver, r.window_from::date as de, r.window_to::date as ate,
       cardinality(r.markets) as mkts, r.bars_evaluated as bars, r.signals as sig,
       r.outcomes_resolved as out, r.outcomes_open as open, r.seconds as seg, r.workers as wk,
       r.decision_lag_s as lag, r.evaluations_by_state::text as estados, r.errors as err
  from replay_runs r join strategy_versions sv on sv.id=r.strategy_version_id
  join strategies s on s.id=sv.strategy_id
 where s.key='mean_reversion'
 order by sv.version, r.window_from;

select level, component, event, left(message,105) as mensagem, created_at
  from system_events
 where created_at >= timestamptz '2026-09-08 21:20:00+00'
   and (component in ('activate_strategy_version','replay_engine')
        or message ilike '%mean_reversion%')
 order by created_at;
commit;
