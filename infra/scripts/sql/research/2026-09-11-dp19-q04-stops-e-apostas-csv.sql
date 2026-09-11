-- D-P19 q04 — dump CSV: por mercado, a distância de stop que a família usa e as apostas únicas
-- Somente leitura. Uma linha por (symbol, tipo) + uma linha 'FAMILIA/todos' com o agregado.
-- Colunas: escopo, symbol, tipo, n_desfechos, d_stop_p10, d_stop_p50, d_stop_p90,
--          apostas_unicas, dias_com_aposta, r_soma, r_medio, acertos, com_r
-- Dedupe da aposta = (market_id, meta.entry_plan.source_bar_close), vence activated_at mais antigo
-- (T3.78). d_stop = meta.excursions.initial_risk / virtual_entry.
-- Uso:
--   ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter -v ON_ERROR_STOP=1 -q -f -" \
--     < este arquivo > .claude/state/exp-drafts/dp19/stops_e_apostas.csv
begin transaction isolation level repeatable read read only;

copy (
  with desfechos as (
    select so.signal_id,
           sig.market_id,
           m.symbol,
           m.market_type::text as tipo,
           sv.activated_at,
           sv.id as strategy_version_id,
           (so.meta->'entry_plan'->>'source_bar_close')::timestamptz as source_bar_close,
           (so.entry_ts at time zone 'America/Sao_Paulo')::date as dia_brt,
           so.r_multiple,
           (so.meta->'excursions'->>'initial_risk')::numeric / nullif(so.virtual_entry, 0) as d_stop
      from signal_outcomes so
      join agent_signals sig on sig.id = so.signal_id
      join strategy_versions sv on sv.id = sig.strategy_version_id
      join strategies s on s.id = sv.strategy_id
      join markets m on m.id = sig.market_id
     where so.meta->>'cohort' = 'prospective'
       and so.tracking_state = 'terminal'
       and so.entry_ts >= now() - interval '30 days'
       and s.key like 'mean_reversion%'
  ), unicas as (
    select distinct on (market_id, source_bar_close) *
      from desfechos
     order by market_id, source_bar_close, activated_at asc, strategy_version_id, signal_id
  ), stops as (
    select symbol, tipo, count(*) filter (where d_stop is not null) as n_desfechos,
           (percentile_cont(0.10) within group (order by d_stop))::numeric as d_stop_p10,
           (percentile_cont(0.50) within group (order by d_stop))::numeric as d_stop_p50,
           (percentile_cont(0.90) within group (order by d_stop))::numeric as d_stop_p90
      from desfechos group by 1, 2
  ), apostas as (
    select symbol, tipo, count(*) as apostas_unicas,
           count(distinct dia_brt) as dias_com_aposta,
           sum(r_multiple) as r_soma,
           avg(r_multiple) as r_medio,
           count(*) filter (where r_multiple > 0) as acertos,
           count(*) filter (where r_multiple is not null) as com_r
      from unicas group by 1, 2
  )
  select 'mercado' as escopo, s.symbol as symbol, s.tipo as tipo,
         s.n_desfechos as n_desfechos,
         round(s.d_stop_p10, 8) as d_stop_p10,
         round(s.d_stop_p50, 8) as d_stop_p50,
         round(s.d_stop_p90, 8) as d_stop_p90,
         coalesce(a.apostas_unicas, 0) as apostas_unicas,
         coalesce(a.dias_com_aposta, 0) as dias_com_aposta,
         round(a.r_soma, 6) as r_soma,
         round(a.r_medio, 6) as r_medio,
         coalesce(a.acertos, 0) as acertos,
         coalesce(a.com_r, 0) as com_r
    from stops s left join apostas a on a.symbol = s.symbol and a.tipo = s.tipo
  union all
  select 'FAMILIA', 'todos', 'todos',
         (select count(*) from desfechos where d_stop is not null),
         (select round((percentile_cont(0.10) within group (order by d_stop))::numeric, 8) from desfechos),
         (select round((percentile_cont(0.50) within group (order by d_stop))::numeric, 8) from desfechos),
         (select round((percentile_cont(0.90) within group (order by d_stop))::numeric, 8) from desfechos),
         (select count(*) from unicas),
         (select count(distinct dia_brt) from unicas),
         (select round(sum(r_multiple), 6) from unicas),
         (select round(avg(r_multiple), 6) from unicas),
         (select count(*) from unicas where r_multiple > 0),
         (select count(*) from unicas where r_multiple is not null)
  order by 1, 2, 3
) to stdout with (format csv, header true);

commit;
