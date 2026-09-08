-- T3.42 q21 — a identidade do pedagio conferida decisao a decisao:
-- custo_R previsto = 0,0020 / (stop_atr x ATR%) com stop_atr = 1 no mean_reversion_v1.
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;
with pop as (
  select left(split_part(o.meta->>'cohort',':',2),8) as coorte,
         (a.supporting_features->'atr'->>'percent')::numeric as atr_pct,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'progress'->>'exit_base')::numeric as exit_base,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk,
         (o.meta->>'r_ex_funding')::numeric as r_exf
    from signal_outcomes o join agent_signals a on a.id=o.signal_id
   where o.meta->>'cohort' in ('replay:d0f77894-1e04-454e-a49f-d9a98d894968',
                               'replay:d570b19a-f6e2-4312-86ed-9394b16ac81a',
                               'replay:f4af4ffe-da8b-47e4-9ad2-6af83aca59e4')
), c as (
  select coorte, atr_pct,
         (exit_base - p_entry/1.0006)/risk - r_exf as custo_r_medido,
         0.0020 / atr_pct as custo_r_previsto
    from pop
)
select coorte, count(*) as n,
       round(avg(custo_r_medido),4) as custo_medio_medido,
       round(max(custo_r_medido),4) as custo_max_medido,
       round(avg(custo_r_previsto),4) as custo_medio_previsto,
       round(max(custo_r_previsto),4) as custo_max_previsto,
       round(max(abs(custo_r_medido - custo_r_previsto)),4) as maior_erro_absoluto
  from c group by 1 order by 1;
commit;
