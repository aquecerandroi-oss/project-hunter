-- T3.32 — o custo em R não é uma correlação, é uma identidade:
--   custo_R = (2*cost_bps + fee*(P_entry+P_exit)/P) / risco  ~=  0,0020 / (risco/preço)
-- com cost_bps = spread/2 + slippage = 6 bps por perna e fee = 4 bps por perna.
-- A coluna `custo_r_x_risco_pct` tem de ficar colada em 0,0020 para a identidade valer.
-- Inclui a contagem de `censored` (bucket do item 1) e o dinheiro por operação a
-- 0,25 % de 19 333 USDT = 48,33 USDT por R.
\pset border 2
\pset numericlocale off
with pop as (
  select s.key||' '||sv.version as version,
         case when o.meta->>'cohort' like 'replay:%' then 'replay:'||left(split_part(o.meta->>'cohort',':',2),8)
              else 'prospective' end as coorte,
         o.tracking_state, o.result, o.r_multiple as r_net,
         (o.meta->>'r_ex_funding')::numeric as r_exf,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'progress'->>'exit_base')::numeric as exit_base,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk
  from signal_outcomes o
  join agent_signals a on a.id=o.signal_id
  join strategy_versions sv on sv.id=a.strategy_version_id
  join strategies s on s.id=sv.strategy_id
  where a.emitted_at < timestamptz '2026-09-08 15:00:00+00'
), d as (
  select *, risk/(p_entry/1.0006) as risco_pct,
            (exit_base-p_entry/1.0006)/risk - r_exf as custo_r
  from pop where tracking_state='terminal' and r_net is not null and risk>0
)
select version, coorte, count(*) n,
       round(avg(custo_r*risco_pct),6) as custo_r_x_risco_pct,
       round(stddev_samp(custo_r*risco_pct),7) as desvio,
       round(avg(custo_r),4) custo_r_med,
       round(avg(custo_r)*48.33,2) as custo_usdt_por_op,
       round(avg(r_net)*48.33,2) as resultado_usdt_por_op,
       round(sum(r_net)*48.33,2) as resultado_usdt_total
from d group by 1,2 having count(*)>=20 order by 1,2;
\echo ''
\echo '== censurados e sem funding (buckets que nao aparecem no item 1) =='
select s.key||' '||sv.version as version,
       case when o.meta->>'cohort' like 'replay:%' then 'replay:'||left(split_part(o.meta->>'cohort',':',2),8)
            else 'prospective' end as coorte,
       count(*) filter (where o.tracking_state='censored') as censurados,
       count(*) filter (where o.tracking_state='terminal' and o.r_multiple is null) as terminal_sem_funding,
       count(*) filter (where o.tracking_state='terminal') as terminais
from signal_outcomes o
join agent_signals a on a.id=o.signal_id
join strategy_versions sv on sv.id=a.strategy_version_id
join strategies s on s.id=sv.strategy_id
where a.emitted_at < timestamptz '2026-09-08 15:00:00+00'
group by 1,2 having count(*)>=20 order by 1,2;
