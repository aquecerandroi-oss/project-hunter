-- T3.32 item 1c — por hora do dia (America/Sao_Paulo) e por dia.
\pset border 2
\pset numericlocale off
\echo '== 6a. por hora de Brasilia (entrada) =='
with pop as (
  select s.key||' '||sv.version as version,
         case when o.meta->>'cohort' like 'replay:%' then 'replay:'||left(split_part(o.meta->>'cohort',':',2),8)
              else 'prospective' end as coorte,
         o.result, o.r_multiple as r_net,
         (o.meta->>'r_ex_funding')::numeric as r_exf,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'progress'->>'exit_base')::numeric as exit_base,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk,
         extract(hour from (o.entry_ts at time zone 'America/Sao_Paulo')) as hora_br,
         (o.entry_ts at time zone 'America/Sao_Paulo')::date as dia_br
  from signal_outcomes o
  join agent_signals a on a.id=o.signal_id
  join strategy_versions sv on sv.id=a.strategy_version_id
  join strategies s on s.id=sv.strategy_id
  where a.emitted_at < timestamptz '2026-09-08 15:00:00+00'  -- corte declarado da leitura
    and o.tracking_state='terminal' and o.r_multiple is not null
), d as (
  select *, (exit_base-p_entry/1.0006)/risk as r_gross,
            (exit_base-p_entry/1.0006)/risk - r_exf as custo_r
  from pop where risk>0
)
select version, coorte, hora_br::int as hora_br, count(*) n,
       round(avg(r_gross),3) bruto, round(avg(custo_r),3) custo,
       round(avg(r_net),3) liquido, round(sum(r_net),2) soma_r,
       round(100.0*count(*) filter (where result='target')/count(*),1) acerto
from d
where (version,coorte) in (('momentum v2','replay:f8d8279c'),('volume_anomaly v2','replay:bac27c12'))
group by 1,2,3 order by 1,2,3;
\echo ''
\echo '== 6b. por dia (janela de replay, Brasilia) — 8 piores e 3 melhores por populacao =='
with pop as (
  select s.key||' '||sv.version as version,
         case when o.meta->>'cohort' like 'replay:%' then 'replay:'||left(split_part(o.meta->>'cohort',':',2),8)
              else 'prospective' end as coorte,
         o.result, o.r_multiple as r_net,
         (o.entry_ts at time zone 'America/Sao_Paulo')::date as dia_br
  from signal_outcomes o
  join agent_signals a on a.id=o.signal_id
  join strategy_versions sv on sv.id=a.strategy_version_id
  join strategies s on s.id=sv.strategy_id
  where a.emitted_at < timestamptz '2026-09-08 15:00:00+00'  -- corte declarado da leitura
    and o.tracking_state='terminal' and o.r_multiple is not null
), agg as (
  select version, coorte, dia_br, count(*) n, round(sum(r_net),2) soma_r, round(avg(r_net),3) liquido
  from pop
  where (version,coorte) in (('momentum v2','replay:f8d8279c'),('volume_anomaly v2','replay:bac27c12'))
  group by 1,2,3
), rk as (
  select *, row_number() over (partition by version,coorte order by soma_r) pior,
            row_number() over (partition by version,coorte order by soma_r desc) melhor,
            count(*) over (partition by version,coorte) dias,
            sum(soma_r) over (partition by version,coorte) total
  from agg
)
select version, coorte, dias, total, dia_br, n, soma_r, liquido,
       case when pior<=8 then 'pior '||pior else 'melhor '||melhor end pos
from rk where pior<=8 or melhor<=3 order by version, coorte, soma_r;
