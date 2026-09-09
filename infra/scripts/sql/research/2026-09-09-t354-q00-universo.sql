-- T3.54 q00 — o universo candidato para o eixo de timeframe: perpetuas monitoradas
-- da binance com cobertura de velas de 1 min na janela de 31 d (2026-08-08 -> 2026-09-08),
-- ordenadas por liquidez. Serve para escolher os 4 + 12 mercados de q01/q02 sem
-- inventar nome nenhum. SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

with janela as (
  select timestamptz '2026-08-08 00:00:00+00' as ini,
         timestamptz '2026-09-08 00:00:00+00' as fim
), cand as (
  select m.id, m.symbol, m.market_type::text as tipo, m.is_monitored,
         m.monitor_rank, m.volume_24h_usd
    from markets m
    join exchanges e on e.id = m.exchange_id
   where e.code = 'binance' and m.market_type = 'perpetual' and m.delisted_at is null
), cob as (
  select c.market_id, count(*) as minutos_finais,
         min(c.open_time) as primeiro, max(c.open_time) as ultimo
    from candles c, janela j
   where c.timeframe = '1m' and c.is_final
     and c.open_time >= j.ini and c.open_time < j.fim
     and c.market_id in (select id from cand)
   group by 1
)
select cand.symbol, cand.monitor_rank,
       round(cand.volume_24h_usd/1e6, 1) as vol24h_musd,
       coalesce(cob.minutos_finais, 0) as minutos,
       round(100.0*coalesce(cob.minutos_finais,0)/44640.0, 2) as cobertura_pct,
       cob.primeiro, cob.ultimo
  from cand left join cob on cob.market_id = cand.id
 where cand.is_monitored
 order by cand.volume_24h_usd desc nulls last
 limit 40;
commit;
