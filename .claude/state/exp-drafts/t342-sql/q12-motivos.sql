-- T3.42 q12 — motivos de saida por coorte (populacao inteira) e cobertura.
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;
with pop as (
  select left(split_part(o.meta->>'cohort',':',2),8) as coorte,
         o.result::text as motivo, o.tracking_state::text as estado,
         o.r_multiple as r_net,
         (o.meta->>'r_ex_funding')::numeric as r_exf,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'progress'->>'exit_base')::numeric as exit_base,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk,
         (o.meta->'excursions'->>'mfe')::numeric as mfe_price,
         (a.supporting_features->'atr'->>'percent')::numeric as atr_pct,
         (o.meta->'entry_plan'->>'source_bar_close')::timestamptz as bar
    from signal_outcomes o join agent_signals a on a.id=o.signal_id
   where o.meta->>'cohort' in ('replay:d0f77894-1e04-454e-a49f-d9a98d894968',
                               'replay:d570b19a-f6e2-4312-86ed-9394b16ac81a',
                               'replay:f4af4ffe-da8b-47e4-9ad2-6af83aca59e4')
)
select coorte, motivo, count(*) as n,
       round(100.0*count(*)/sum(count(*)) over (partition by coorte),1) as pct,
       round(avg(r_net),4) as r_liq_medio, round(sum(r_net),2) as r_liq_soma,
       round(avg((exit_base - p_entry/1.0006)/risk),4) as r_bruto_medio
  from pop group by 1,2 order by 1, n desc;

commit;
