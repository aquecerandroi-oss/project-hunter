-- T3.32 itens 3 e 4 — invalidação (KB-0006) e geometria MFE/MAE em R.
-- MFE/MAE vêm de meta.excursions (unidade "price", método ohlc_complete_bars_v1)
-- divididos por meta.excursions.initial_risk para virarem R.
-- ATENÇÃO: o MFE de um trade invalidado só cobre até a saída — por construção não
-- responde "teria batido o alvo se deixado em paz"; isso é o braço INV-B do replay.
\pset border 2
\pset numericlocale off
\echo '== 3a. invalidacao: quantos, com que R, e quantos foram ganhadores =='
with pop as (
  select o.signal_id, s.key||' '||sv.version as version,
         case when o.meta->>'cohort' like 'replay:%' then 'replay:'||left(split_part(o.meta->>'cohort',':',2),8)
              else 'prospective' end as coorte,
         o.result, o.r_multiple as r_net,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk,
         (o.meta->'excursions'->>'mfe_complete_bars')::numeric as mfe_px,
         (o.meta->'excursions'->>'mae_complete_bars')::numeric as mae_px,
         (o.meta->'progress'->>'bars_in_position')::int as barras
  from signal_outcomes o
  join agent_signals a on a.id=o.signal_id
  join strategy_versions sv on sv.id=a.strategy_version_id
  join strategies s on s.id=sv.strategy_id
  where a.emitted_at < timestamptz '2026-09-08 15:00:00+00'  -- corte declarado da leitura
    and o.tracking_state='terminal' and o.r_multiple is not null
), d as (
  select *, mfe_px/risk as mfe_r, mae_px/risk as mae_r,
         case when r_net>0 then 'ganhador' else 'perdedor' end as lado
  from pop where risk>0
)
select version, coorte,
       count(*) filter (where result='invalidated') as n_inval,
       round(100.0*count(*) filter (where result='invalidated')/count(*),1) as pct_inval,
       count(*) filter (where result='invalidated' and r_net>0) as inval_ganhadores,
       round(sum(r_net) filter (where result='invalidated'),2) as soma_r_inval,
       round(avg(mfe_r) filter (where result='invalidated'),3) as mfe_r_med_inval,
       round(max(mfe_r) filter (where result='invalidated'),3) as mfe_r_max_inval,
       round(avg(barras) filter (where result='invalidated'),1) as barras_med_inval,
       round(100.0*count(*) filter (where result='invalidated' and mfe_r>=1.0)/nullif(count(*) filter (where result='invalidated'),0),1) as pct_inval_mfe_ge_1r
from d group by 1,2 having count(*)>=20 order by 1,2;
\echo ''
\echo '== 4a. MFE/MAE em R por lado (percentis) =='
with pop as (
  select o.signal_id, s.key||' '||sv.version as version,
         case when o.meta->>'cohort' like 'replay:%' then 'replay:'||left(split_part(o.meta->>'cohort',':',2),8)
              else 'prospective' end as coorte,
         o.result, o.r_multiple as r_net,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk,
         (o.meta->'excursions'->>'mfe_complete_bars')::numeric as mfe_px,
         (o.meta->'excursions'->>'mae_complete_bars')::numeric as mae_px
  from signal_outcomes o
  join agent_signals a on a.id=o.signal_id
  join strategy_versions sv on sv.id=a.strategy_version_id
  join strategies s on s.id=sv.strategy_id
  where a.emitted_at < timestamptz '2026-09-08 15:00:00+00'  -- corte declarado da leitura
    and o.tracking_state='terminal' and o.r_multiple is not null
), d as (
  select *, mfe_px/risk as mfe_r, mae_px/risk as mae_r,
         case when r_net>0 then 'ganhador' else 'perdedor' end as lado
  from pop where risk>0
)
select version, coorte, lado, count(*) n,
       round(percentile_cont(0.50) within group (order by mfe_r)::numeric,3) as mfe_p50,
       round(percentile_cont(0.60) within group (order by mfe_r)::numeric,3) as mfe_p60,
       round(percentile_cont(0.75) within group (order by mfe_r)::numeric,3) as mfe_p75,
       round(percentile_cont(0.90) within group (order by mfe_r)::numeric,3) as mfe_p90,
       round(percentile_cont(0.50) within group (order by mae_r)::numeric,3) as mae_p50,
       round(percentile_cont(0.75) within group (order by mae_r)::numeric,3) as mae_p75,
       round(percentile_cont(0.90) within group (order by mae_r)::numeric,3) as mae_p90,
       round(max(mae_r),3) as mae_max
from d
where (version,coorte) in (('momentum v2','prospective'),('momentum v2','replay:f8d8279c'),
                           ('volume_anomaly v2','prospective'),('volume_anomaly v2','replay:bac27c12'))
group by 1,2,3 order by 1,2,3;
