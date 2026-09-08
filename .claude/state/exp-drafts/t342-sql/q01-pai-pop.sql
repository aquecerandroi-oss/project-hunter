-- T3.42 q01 — populacao do pai (mean_reversion v1, coorte replay:d0f77894) e a distribuicao de ATR%.
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;

select r.run_id, s.key||' '||sv.version as versao, r.window_from::date as de, r.window_to::date as ate,
       cardinality(r.markets) as mkts, r.bars_evaluated, r.signals, r.outcomes_resolved, r.outcomes_open,
       r.seconds, r.workers, r.decision_lag_s, r.evaluations_by_state, r.errors
  from replay_runs r
  join strategy_versions sv on sv.id = r.strategy_version_id
  join strategies s on s.id = sv.strategy_id
 where r.cohort = 'replay:d0f77894-1e04-454e-a49f-d9a98d894968'
 order by r.window_from;

with pop as (
  select a.market_id, m.symbol,
         (o.meta->'entry_plan'->>'source_bar_close')::timestamptz as bar,
         o.result::text as motivo, o.tracking_state::text as estado,
         o.r_multiple as r_net,
         (o.meta->>'r_ex_funding')::numeric as r_exf,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'progress'->>'exit_base')::numeric as exit_base,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk,
         (a.supporting_features->'atr'->>'percent')::numeric as atr_pct
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join markets m on m.id = a.market_id
   where o.meta->>'cohort' = 'replay:d0f77894-1e04-454e-a49f-d9a98d894968'
)
select count(*) as decisoes,
       count(*) filter (where estado='terminal' and r_net is not null) as avaliaveis,
       count(*) filter (where atr_pct is null) as sem_atr,
       round(min(atr_pct),5) as atr_min, round(max(atr_pct),5) as atr_max,
       round((percentile_cont(0.5) within group (order by atr_pct))::numeric,5) as atr_p50,
       count(*) filter (where atr_pct >= 0.008) as n_acima_0008,
       count(*) filter (where atr_pct >= 0.010) as n_acima_0010,
       count(distinct bar::date) as dias
  from pop;
commit;
