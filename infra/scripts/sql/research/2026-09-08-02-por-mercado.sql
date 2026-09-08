-- T3.32 item 1b — por mercado (10 piores e 10 melhores em soma de R_net).
\pset border 2
\pset numericlocale off
with pop as (
  select o.signal_id, s.key||' '||sv.version as version,
         case when o.meta->>'cohort' like 'replay:%' then 'replay:'||left(split_part(o.meta->>'cohort',':',2),8)
              else 'prospective' end as coorte,
         m.symbol, o.result,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'progress'->>'exit_base')::numeric as exit_base,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk,
         o.r_multiple as r_net, (o.meta->>'r_ex_funding')::numeric as r_exf
  from signal_outcomes o
  join agent_signals a on a.id=o.signal_id
  join strategy_versions sv on sv.id=a.strategy_version_id
  join strategies s on s.id=sv.strategy_id
  join markets m on m.id=a.market_id
  where a.emitted_at < timestamptz '2026-09-08 15:00:00+00'  -- corte declarado da leitura
    and o.tracking_state='terminal' and o.r_multiple is not null
), d as (
  select *, (exit_base - p_entry/1.0006)/risk as r_gross,
            (exit_base - p_entry/1.0006)/risk - r_exf as custo_r,
            risk/(p_entry/1.0006) as risco_pct
  from pop where risk>0
), agg as (
  select version, coorte, symbol, count(*) n,
         round(sum(r_net),2) soma_r, round(avg(r_net),4) med_r,
         round(avg(r_gross),4) bruto, round(avg(custo_r),4) custo,
         round(100*avg(risco_pct),3) risco_pct_preco,
         round(100.0*count(*) filter (where result='target')/count(*),1) acerto
  from d group by 1,2,3
), rk as (
  select *, row_number() over (partition by version,coorte order by soma_r) as pior,
            row_number() over (partition by version,coorte order by soma_r desc) as melhor,
            count(*) over (partition by version,coorte) as mercados
  from agg
)
select version, coorte, symbol, n, soma_r, med_r, bruto, custo, risco_pct_preco, acerto,
       case when pior<=10 then 'pior '||pior else 'melhor '||melhor end as posicao
from rk
where (pior<=10 or melhor<=10)
  and (version,coorte) in (('momentum v2','prospective'),('momentum v2','replay:f8d8279c'),
                           ('volume_anomaly v2','prospective'),('volume_anomaly v2','replay:bac27c12'))
order by version, coorte, soma_r;
