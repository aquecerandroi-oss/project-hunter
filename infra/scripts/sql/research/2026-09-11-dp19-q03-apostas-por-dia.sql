-- D-P19 q03 — apostas únicas por dia (BRT) e por mercado, e o R por aposta (somente leitura)
-- Dedupe conforme T3.78: chave (market_id, meta.entry_plan.source_bar_close); vence a versão com
-- activated_at mais antigo, desempate por strategy_version_id e signal_id.
begin transaction isolation level repeatable read read only;

with desfechos as (
  select so.signal_id,
         sig.market_id,
         m.symbol,
         m.market_type::text as tipo,
         s.key as familia,
         sv.version,
         sv.activated_at,
         sv.id as strategy_version_id,
         (so.meta->'entry_plan'->>'source_bar_close')::timestamptz as source_bar_close,
         (so.entry_ts at time zone 'America/Sao_Paulo')::date as dia_brt,
         extract(hour from (so.entry_ts at time zone 'America/Sao_Paulo'))::int as hora_brt,
         so.r_multiple,
         so.result::text as resultado,
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
)
select 'por dia' as bloco, dia_brt::text as chave, null::text as chave2,
       count(*) as apostas_unicas,
       count(*) filter (where r_multiple is not null) as com_r,
       round(sum(r_multiple), 4) as soma_r,
       round(avg(r_multiple), 4) as media_r,
       round(100.0 * count(*) filter (where r_multiple > 0) / nullif(count(*) filter (where r_multiple is not null), 0), 1) as acerto_pct,
       count(distinct symbol) as mercados
  from unicas group by 2
union all
select 'por mercado', symbol, tipo,
       count(*), count(*) filter (where r_multiple is not null),
       round(sum(r_multiple), 4), round(avg(r_multiple), 4),
       round(100.0 * count(*) filter (where r_multiple > 0) / nullif(count(*) filter (where r_multiple is not null), 0), 1),
       count(distinct dia_brt)
  from unicas group by 2, 3
union all
select 'pooled x unicas', 'total', null,
       (select count(*) from unicas), (select count(*) from desfechos),
       (select round(sum(r_multiple), 4) from unicas), (select round(sum(r_multiple), 4) from desfechos),
       null, null
 order by 1, 2;

\echo '== apostas únicas por dia x mercado, só os 16 do universo executável =='
with desfechos as (
  select so.signal_id, sig.market_id, m.symbol, sv.activated_at, sv.id as strategy_version_id,
         (so.meta->'entry_plan'->>'source_bar_close')::timestamptz as source_bar_close,
         (so.entry_ts at time zone 'America/Sao_Paulo')::date as dia_brt,
         so.r_multiple
    from signal_outcomes so
    join agent_signals sig on sig.id = so.signal_id
    join strategy_versions sv on sv.id = sig.strategy_version_id
    join strategies s on s.id = sv.strategy_id
    join markets m on m.id = sig.market_id
   where so.meta->>'cohort' = 'prospective'
     and so.tracking_state = 'terminal'
     and so.entry_ts >= now() - interval '30 days'
     and s.key like 'mean_reversion%'
     and m.symbol in ('ARBUSDT','BNBUSDT','BTCUSDT','DASHUSDT','DOGEUSDT','ETHUSDT','LINKUSDT',
                      'NEARUSDT','PROMUSDT','SAHARAUSDT','SOLUSDT','SUIUSDT','TAOUSDT','UNIUSDT',
                      'XRPUSDT','ZECUSDT')
), unicas as (
  select distinct on (market_id, source_bar_close) *
    from desfechos
   order by market_id, source_bar_close, activated_at asc, strategy_version_id, signal_id
)
select dia_brt, count(*) as apostas_unicas, count(distinct symbol) as mercados,
       round(sum(r_multiple), 4) as soma_r,
       string_agg(distinct symbol, ' ') as simbolos
  from unicas group by 1 order by 1;

commit;
