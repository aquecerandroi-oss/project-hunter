-- D-P19 q02 — a distância de stop que a família de fato usa, por mercado (somente leitura)
-- Fonte: signal_outcomes da coorte prospectiva, terminal, família mean_reversion*.
-- d_stop = meta.excursions.initial_risk / virtual_entry  (fração do preço de entrada)
-- d_efetiva = d_stop + hunter_risk.sizing.round_trip_cost_fraction(meta.assumed_costs)
--             = d_stop + 2*(spread/2 + slippage + fee)/1e4 = d_stop + 0,0020 com a hipotese do Lab,
-- que é o denominador do sizing do motor (docs/RISK_ENGINE.md §4).
begin transaction isolation level repeatable read read only;

\echo '== 1. d_stop por mercado (mediana, p10, p90) + custo declarado =='
with base as (
  select m.symbol,
         m.market_type::text as tipo,
         (so.meta->'excursions'->>'initial_risk')::numeric / nullif(so.virtual_entry, 0) as d_stop,
         2 * ((so.meta->'assumed_costs'->>'spread_bps')::numeric / 2
              + (so.meta->'assumed_costs'->>'slippage_bps')::numeric
              + (so.meta->'assumed_costs'->>'fee_bps')::numeric) / 10000 as custo_rt,
         abs(so.virtual_entry - so.virtual_stop) / nullif(so.virtual_entry, 0) as d_stop_check
    from signal_outcomes so
    join agent_signals sig on sig.id = so.signal_id
    join strategy_versions sv on sv.id = sig.strategy_version_id
    join strategies s on s.id = sv.strategy_id
    join markets m on m.id = sig.market_id
   where so.meta->>'cohort' = 'prospective'
     and so.tracking_state = 'terminal'
     and so.entry_ts >= now() - interval '30 days'
     and s.key like 'mean_reversion%'
     and (so.meta->'excursions'->>'initial_risk') is not null
)
select symbol, tipo, count(*) as n,
       round(percentile_cont(0.10) within group (order by d_stop)::numeric, 6) as d_stop_p10,
       round(percentile_cont(0.50) within group (order by d_stop)::numeric, 6) as d_stop_p50,
       round(percentile_cont(0.90) within group (order by d_stop)::numeric, 6) as d_stop_p90,
       round(max(custo_rt)::numeric, 6) as custo_rt,
       round(percentile_cont(0.50) within group (order by d_stop_check)::numeric, 6) as d_stop_p50_pelos_precos
  from base
 group by 1, 2
 order by 1, 2;

\echo '== 2. d_stop agregado da família (a mediana única) =='
with base as (
  select (so.meta->'excursions'->>'initial_risk')::numeric / nullif(so.virtual_entry, 0) as d_stop
    from signal_outcomes so
    join agent_signals sig on sig.id = so.signal_id
    join strategy_versions sv on sv.id = sig.strategy_version_id
    join strategies s on s.id = sv.strategy_id
   where so.meta->>'cohort' = 'prospective'
     and so.tracking_state = 'terminal'
     and so.entry_ts >= now() - interval '30 days'
     and s.key like 'mean_reversion%'
     and (so.meta->'excursions'->>'initial_risk') is not null
)
select count(*) as n,
       round(percentile_cont(0.10) within group (order by d_stop)::numeric, 6) as p10,
       round(percentile_cont(0.50) within group (order by d_stop)::numeric, 6) as p50,
       round(percentile_cont(0.90) within group (order by d_stop)::numeric, 6) as p90,
       count(*) filter (where d_stop < 0.003) as fora_da_banda_abaixo,
       count(*) filter (where d_stop > 0.03) as fora_da_banda_acima
  from base;

commit;
