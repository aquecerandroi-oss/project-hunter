-- T3.47 q10 — populacoes: os tres pais e as seis variantes de stop largo, mesma janela
-- (2026-08-08..2026-09-08) e os mesmos quatro mercados. Somente leitura.
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;
with pop as (
  select s.key||' '||sv.version as versao,
         left(split_part(o.meta->>'cohort',':',2),8) as coorte,
         a.market_id,
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
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
   where o.meta->>'cohort' in (
     'replay:d0f77894-1e04-454e-a49f-d9a98d894968',  -- mean_reversion v1 (avo)
     'replay:d570b19a-f6e2-4312-86ed-9394b16ac81a',  -- mean_reversion v2 (pai B)
     'replay:f4af4ffe-da8b-47e4-9ad2-6af83aca59e4',  -- mean_reversion v3 (pai A)
     'replay:9a08835a-ae13-4c23-b521-734b2f60a3a2',  -- momentum v6 (pai C)
     'replay:f8d8279c-1d8c-4d31-9a0c-9a95ba5cbd45',  -- momentum v2 (avo)
     'replay:af24ee08-01cf-41ba-9b7a-1b43172bea28',  -- mean_reversion v4 = v3 x1,5
     'replay:66fa85cb-1d51-4330-a00b-00964b430ab4',  -- mean_reversion v5 = v3 x2
     'replay:9d99748b-21b9-44a7-8980-32c37b931e6e',  -- mean_reversion v6 = v2 x1,5
     'replay:264b227f-5bc0-4930-8c5b-2e883c0a858e',  -- mean_reversion v7 = v2 x2
     'replay:293d98b7-90e1-4dfe-a604-60556f3b175e',  -- momentum v7 = v6 x1,5
     'replay:ee11d60b-3a4e-48be-94a3-1aecb8cf16fd')  -- momentum v8 = v6 x2
)
select versao, coorte,
       count(*) as decisoes,
       count(*) filter (where estado='terminal' and r_net is not null) as avaliaveis,
       round(avg((exit_base - p_entry/1.0006)/risk) filter (where risk>0), 4) as exp_bruta_r,
       round(avg((exit_base - p_entry/1.0006)/risk - r_exf) filter (where risk>0), 4) as custo_r,
       round(avg(r_net) filter (where r_net is not null), 4) as exp_liquida_r,
       round(sum(r_net) filter (where r_net is not null), 2) as soma_r,
       round(100.0*count(*) filter (where motivo='target')/nullif(count(*) filter (where estado='terminal'),0), 1) as acerto_pct,
       round(sum(r_net) filter (where r_net>0) / nullif(-sum(r_net) filter (where r_net<0),0), 4) as pf_liquido,
       round(sum((exit_base - p_entry/1.0006)/risk) filter (where risk>0 and (exit_base - p_entry/1.0006)/risk>0)
             / nullif(-sum((exit_base - p_entry/1.0006)/risk) filter (where risk>0 and (exit_base - p_entry/1.0006)/risk<0),0), 4) as pf_bruto,
       count(distinct bar::date) as dias,
       round((percentile_cont(0.5) within group (order by risk/nullif(p_entry,0)))::numeric,5) as risco_pct_p50
  from pop group by 1,2 order by 1,2;
commit;
