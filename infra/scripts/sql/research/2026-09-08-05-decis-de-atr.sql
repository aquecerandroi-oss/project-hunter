-- T3.32 item 1d/2 — decil de ATR% na decisão (e o risco inicial em % do preço),
-- que é o denominador do custo em R:  custo_R ~ 0,0020 / (risco/preço).
\pset border 2
\pset numericlocale off
with pop as (
  select o.signal_id, s.key||' '||sv.version as version,
         case when o.meta->>'cohort' like 'replay:%' then 'replay:'||left(split_part(o.meta->>'cohort',':',2),8)
              else 'prospective' end as coorte,
         o.result, o.r_multiple as r_net,
         (o.meta->>'r_ex_funding')::numeric as r_exf,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'progress'->>'exit_base')::numeric as exit_base,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk,
         (a.supporting_features->'atr'->>'value')::numeric as atr0,
         (o.meta->>'reference_price')::numeric as ref_px
  from signal_outcomes o
  join agent_signals a on a.id=o.signal_id
  join strategy_versions sv on sv.id=a.strategy_version_id
  join strategies s on s.id=sv.strategy_id
  where a.emitted_at < timestamptz '2026-09-08 15:00:00+00'  -- corte declarado da leitura
    and o.tracking_state='terminal' and o.r_multiple is not null
), d as (
  select *, atr0/ref_px as atr_pct, risk/(p_entry/1.0006) as risco_pct,
         (exit_base - p_entry/1.0006)/risk as r_gross,
         (exit_base - p_entry/1.0006)/risk - r_exf as custo_r
  from pop where risk>0 and ref_px>0
), q as (
  select *, ntile(10) over (partition by version,coorte order by atr_pct) as decil
  from d
  where (version,coorte) in (('momentum v2','prospective'),('momentum v2','replay:f8d8279c'),
                             ('volume_anomaly v2','prospective'),('volume_anomaly v2','replay:bac27c12'))
)
select version, coorte, decil, count(*) n,
       round(100*min(atr_pct),3) as atr_pct_min,
       round(100*max(atr_pct),3) as atr_pct_max,
       round(100*avg(risco_pct),3) as risco_pct_med,
       round(avg(r_gross),4)  as bruto_r,
       round(avg(custo_r),4)  as custo_r,
       round(avg(r_net),4)    as liquido_r,
       round(sum(r_net),2)    as soma_r,
       round(100.0*count(*) filter (where result='target')/count(*),1) as acerto
from q group by 1,2,3 order by 1,2,3;
