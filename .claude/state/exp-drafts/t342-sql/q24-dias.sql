-- T3.42 q24 — concentracao por dia: soma de R por dia em cada coorte.
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
with pop as (
  select left(split_part(o.meta->>'cohort',':',2),8) as coorte,
         (o.meta->'entry_plan'->>'source_bar_close')::timestamptz::date as dia,
         o.r_multiple as r_net
    from signal_outcomes o join agent_signals a on a.id=o.signal_id
   where o.meta->>'cohort' in ('replay:d0f77894-1e04-454e-a49f-d9a98d894968',
                               'replay:d570b19a-f6e2-4312-86ed-9394b16ac81a',
                               'replay:f4af4ffe-da8b-47e4-9ad2-6af83aca59e4')
)
select dia,
       count(*) filter (where coorte='d0f77894') as n_pai,
       round(sum(r_net) filter (where coorte='d0f77894'),2) as r_pai,
       count(*) filter (where coorte='d570b19a') as n_v1,
       round(sum(r_net) filter (where coorte='d570b19a'),2) as r_v1,
       count(*) filter (where coorte='f4af4ffe') as n_v2,
       round(sum(r_net) filter (where coorte='f4af4ffe'),2) as r_v2
  from pop group by dia order by dia;
commit;
