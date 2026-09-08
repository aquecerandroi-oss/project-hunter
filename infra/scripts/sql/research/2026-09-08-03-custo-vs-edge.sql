-- T3.32 item 2 — expectancy bruta (antes de custo) vs líquida, por versão/coorte.
-- r_gross usa o MESMO denominador (risco inicial congelado) que R_net.
\pset border 2
\pset numericlocale off
with pop as (
  select o.signal_id, s.key||' '||sv.version as version,
         case when o.meta->>'cohort' like 'replay:%' then 'replay:'||left(split_part(o.meta->>'cohort',':',2),8)
              else 'prospective' end as coorte,
         o.result,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'progress'->>'exit_base')::numeric as exit_base,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk,
         o.r_multiple as r_net, (o.meta->>'r_ex_funding')::numeric as r_exf
  from signal_outcomes o
  join agent_signals a on a.id=o.signal_id
  join strategy_versions sv on sv.id=a.strategy_version_id
  join strategies s on s.id=sv.strategy_id
  where a.emitted_at < timestamptz '2026-09-08 15:00:00+00'  -- corte declarado da leitura
    and o.tracking_state='terminal' and o.r_multiple is not null
), d as (
  select *, (exit_base - p_entry/1.0006)/risk as r_gross,
            (exit_base - p_entry/1.0006)/risk - r_exf as custo_r,
            r_exf - r_net as funding_r,
            risk/(p_entry/1.0006) as risco_pct
  from pop where risk>0
)
select version, coorte, count(*) n,
       round(avg(r_gross),4)  as exp_bruta_R,
       round(avg(custo_r),4)  as custo_R,
       round(avg(funding_r),5) as funding_R,
       round(avg(r_net),4)    as exp_liquida_R,
       round(sum(r_net),2)    as soma_R,
       round(sum(r_net)*48.33,2) as usdt_48_33,
       round(100.0*count(*) filter (where result='target')/count(*),1) as acerto_pct,
       round( sum(r_net) filter (where r_net>0) / nullif(-sum(r_net) filter (where r_net<0),0),3) as pf_liquido,
       round( sum(r_gross) filter (where r_gross>0) / nullif(-sum(r_gross) filter (where r_gross<0),0),3) as pf_bruto,
       round(100*avg(risco_pct),3) as risco_pct_preco_med,
       round(100*percentile_cont(0.5) within group (order by risco_pct)::numeric,3) as risco_pct_preco_mediana
from d
group by 1,2
having count(*) >= 20
order by 1,2;
