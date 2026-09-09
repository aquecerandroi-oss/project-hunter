-- T3.62 q01 — cobertura de velas de 1 min dos 16 mercados da T3.54 q00 na janela
-- de 31 d (2026-08-08 -> 2026-09-08) e a profundidade real de cada um
-- (min(open_time)), que e o numero que decide quando um replay de 90 d passa a
-- ser possivel (parte B do brief). SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

with alvo(symbol) as (
  values ('BTCUSDT'),('ETHUSDT'),('ZECUSDT'),('SOLUSDT'),('XRPUSDT'),('BNBUSDT'),
         ('DOGEUSDT'),('SUIUSDT'),('NEARUSDT'),('UNIUSDT'),('ARBUSDT'),('TAOUSDT'),
         ('LINKUSDT'),('DASHUSDT'),('PROMUSDT'),('SAHARAUSDT')
), mkt as (
  select m.id, m.symbol, m.is_monitored, m.monitor_rank
    from markets m
    join exchanges e on e.id = m.exchange_id
   where e.code = 'binance' and m.market_type = 'perpetual'
     and m.symbol in (select symbol from alvo)
), tudo as (
  select c.market_id,
         min(c.open_time) as primeira_vela,
         max(c.open_time) as ultima_vela,
         count(*) as minutos_totais
    from candles c
   where c.timeframe = '1m' and c.is_final
     and c.market_id in (select id from mkt)
   group by 1
), janela as (
  select c.market_id, count(*) as minutos_31d
    from candles c
   where c.timeframe = '1m' and c.is_final
     and c.open_time >= timestamptz '2026-08-08 00:00:00+00'
     and c.open_time <  timestamptz '2026-09-08 00:00:00+00'
     and c.market_id in (select id from mkt)
   group by 1
)
select mkt.symbol, mkt.monitor_rank, mkt.is_monitored,
       coalesce(janela.minutos_31d, 0) as minutos_31d,
       round(100.0*coalesce(janela.minutos_31d,0)/44640.0, 2) as cobertura_31d_pct,
       tudo.primeira_vela, tudo.ultima_vela,
       tudo.minutos_totais,
       round(extract(epoch from (tudo.ultima_vela - tudo.primeira_vela))/86400.0, 2) as alcance_dias
  from mkt
  left join tudo   on tudo.market_id   = mkt.id
  left join janela on janela.market_id = mkt.id
 order by cobertura_31d_pct desc, mkt.symbol;
commit;
