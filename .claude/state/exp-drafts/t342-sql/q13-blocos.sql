-- T3.42 q13 — blocos por dia (media das medias diarias) por coorte.
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;
with pop as (
  select left(split_part(o.meta->>'cohort',':',2),8) as coorte,
         (o.meta->'entry_plan'->>'source_bar_close')::timestamptz::date as dia,
         o.r_multiple as r_net
    from signal_outcomes o join agent_signals a on a.id=o.signal_id
   where o.meta->>'cohort' in ('replay:d0f77894-1e04-454e-a49f-d9a98d894968',
                               'replay:d570b19a-f6e2-4312-86ed-9394b16ac81a',
                               'replay:f4af4ffe-da8b-47e4-9ad2-6af83aca59e4')
), dia as (select coorte, dia, avg(r_net) as m, count(*) as n from pop group by 1,2)
select coorte, count(*) as blocos_dia, round(avg(m),4) as media_das_medias,
       round(stddev_samp(m),4) as desvio,
       round((stddev_samp(m)/sqrt(count(*)::numeric))::numeric,4) as erro_padrao,
       count(*) filter (where m>0) as dias_positivos, count(*) filter (where m<0) as dias_negativos,
       min(n) as min_decisoes_dia, max(n) as max_decisoes_dia
  from dia group by 1 order by 1;
commit;
