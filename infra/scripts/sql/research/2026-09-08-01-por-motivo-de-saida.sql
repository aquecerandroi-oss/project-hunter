-- T3.32 item 1 — para onde vai o dinheiro, por motivo de saída.
-- Somente leitura. Populações: cada (versão, coorte) com >= 20 desfechos.
\pset border 2
\pset numericlocale off
with pop as (
  select o.signal_id,
         s.key||' '||sv.version                                as version,
         case when o.meta->>'cohort' like 'replay:%' then 'replay:'||left(split_part(o.meta->>'cohort',':',2),8)
              else 'prospective' end                           as coorte,
         m.symbol,
         o.tracking_state, o.result, o.no_entry_reason,
         (o.meta->'progress'->>'entry')::numeric               as p_entry,
         o.virtual_stop                                        as stop_px,
         (o.meta->'progress'->>'exit_base')::numeric           as exit_base,
         (o.meta->'excursions'->>'initial_risk')::numeric      as risk,
         o.r_multiple                                          as r_net,
         (o.meta->>'r_ex_funding')::numeric                    as r_exf,
         o.entry_ts, o.exit_ts
  from signal_outcomes o
  join agent_signals a    on a.id  = o.signal_id
  join strategy_versions sv on sv.id = a.strategy_version_id
  join strategies s       on s.id  = sv.strategy_id
  join markets m          on m.id  = a.market_id
  where a.emitted_at < timestamptz '2026-09-08 15:00:00+00'  -- corte declarado da leitura
    and o.tracking_state in ('terminal','no_entry','censored')
), d as (
  select *,
         p_entry/1.0006                                         as open_raw,
         case when risk>0 and exit_base is not null
              then (exit_base - p_entry/1.0006)/risk end        as r_gross,
         case when risk>0 and exit_base is not null
              then (exit_base - p_entry/1.0006)/risk - r_exf end as custo_r,
         case when r_net is not null then r_exf - r_net end      as funding_r,
         extract(epoch from (exit_ts-entry_ts))/60               as dur_min,
         case when tracking_state='no_entry' then 'no_entry:'||coalesce(no_entry_reason,'?')
              when tracking_state='censored' then 'censored'
              when result='expired' then 'horizonte(timeout)'
              else result::text end                             as motivo
  from pop
)
select version, coorte, motivo,
       count(*)                                                        as n,
       round(100.0*count(*)/sum(count(*)) over (partition by version,coorte),1) as pct,
       count(r_net)                                                    as n_aval,
       round(avg(r_net),4)                                             as r_net_med,
       round(sum(r_net),2)                                             as r_net_soma,
       round(avg(r_gross),4)                                           as r_bruto_med,
       round(avg(custo_r),4)                                           as custo_r_med,
       round(avg(funding_r),5)                                         as funding_r_med,
       round(avg(dur_min))                                             as dur_min_med
from d
group by version, coorte, motivo
having (select count(*) from d x where x.version=d.version and x.coorte=d.coorte) >= 20
order by version, coorte, r_net_soma nulls last;
