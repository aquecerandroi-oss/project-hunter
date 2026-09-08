-- T3.42 q10 — populacoes: pai (mean_reversion v1, replay:d0f77894) e as duas variantes.
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;
with pop as (
  select s.key||' '||sv.version as versao,
         'replay:'||left(split_part(o.meta->>'cohort',':',2),8) as coorte,
         a.market_id, m.symbol,
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
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
   where o.meta->>'cohort' in ('replay:d0f77894-1e04-454e-a49f-d9a98d894968',
                               'replay:d570b19a-f6e2-4312-86ed-9394b16ac81a',
                               'replay:f4af4ffe-da8b-47e4-9ad2-6af83aca59e4')
)
select versao, coorte,
       count(*) as decisoes,
       count(*) filter (where estado='terminal' and r_net is not null) as avaliaveis,
       count(*) filter (where risk is null) as sem_risco,
       round(avg((exit_base - p_entry/1.0006)/risk) filter (where risk>0), 4) as exp_bruta_r,
       round(avg((exit_base - p_entry/1.0006)/risk - r_exf) filter (where risk>0), 4) as custo_r,
       round(avg(r_net) filter (where r_net is not null), 4) as exp_liquida_r,
       round(sum(r_net) filter (where r_net is not null), 2) as soma_r,
       round(100.0*count(*) filter (where motivo='target')/nullif(count(*) filter (where estado='terminal'),0), 1) as acerto_pct,
       round(sum(r_net) filter (where r_net>0) / nullif(-sum(r_net) filter (where r_net<0),0), 4) as pf_liquido,
       round(sum((exit_base - p_entry/1.0006)/risk) filter (where risk>0 and (exit_base - p_entry/1.0006)/risk>0)
             / nullif(-sum((exit_base - p_entry/1.0006)/risk) filter (where risk>0 and (exit_base - p_entry/1.0006)/risk<0),0), 4) as pf_bruto,
       count(distinct bar::date) as dias,
       round(min(atr_pct),5) as atr_pct_min_obs, round(max(atr_pct),5) as atr_pct_max_obs
  from pop group by 1,2 order by 1,2;
commit;
