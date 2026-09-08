-- T3.42 q22 — por que o teto e medio e nao garantido: risco inicial / (ATR% x preco de entrada).
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
with pop as (
  select left(split_part(o.meta->>'cohort',':',2),8) as coorte,
         (a.supporting_features->'atr'->>'percent')::numeric as atr_pct,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk
    from signal_outcomes o join agent_signals a on a.id=o.signal_id
   where o.meta->>'cohort' in ('replay:d0f77894-1e04-454e-a49f-d9a98d894968',
                               'replay:d570b19a-f6e2-4312-86ed-9394b16ac81a',
                               'replay:f4af4ffe-da8b-47e4-9ad2-6af83aca59e4')
)
select coorte, count(*) as n,
       round(min(risk/(atr_pct*p_entry)),4) as razao_min,
       round(avg(risk/(atr_pct*p_entry)),4) as razao_media,
       round(max(risk/(atr_pct*p_entry)),4) as razao_max
  from pop group by 1 order by 1;
commit;
