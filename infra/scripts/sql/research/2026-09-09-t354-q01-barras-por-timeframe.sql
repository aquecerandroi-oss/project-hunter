-- T3.54 q01 — as velas de 15 m, 1 h e 4 h dos 16 mercados com 31 d de 1 min
-- (2026-08-08 -> 2026-09-08), dobradas no servidor com exigencia de completude
-- (mesma regra do beta_repo.bar_closes / PIPELINE 2b item 2: apenas is_final,
-- count(*) = n_minutos e o ultimo minuto exatamente em bucket + n-1 min).
-- Saida CSV para o stdout: o Wilder ATR-14 e calculado FORA daqui, pelo mesmo
-- hunter_core.strategies.indicators.wilder_atr que as estrategias usam --
-- reimplementar Wilder em SQL seria um segundo calculo com liberdade para
-- discordar do que decide. SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset format csv
\pset tuples_only off

with janela as (
  select timestamptz '2026-08-08 00:00:00+00' as ini,
         timestamptz '2026-09-08 00:00:00+00' as fim
), sel as (
  select m.id, m.symbol
    from markets m join exchanges e on e.id = m.exchange_id
   where e.code = 'binance' and m.market_type = 'perpetual'
     and m.symbol in ('BTCUSDT','ETHUSDT','ZECUSDT','SOLUSDT','XRPUSDT','BNBUSDT',
                      'DOGEUSDT','SUIUSDT','NEARUSDT','UNIUSDT','ARBUSDT','TAOUSDT',
                      'LINKUSDT','DASHUSDT','PROMUSDT','SAHARAUSDT')
), min1 as (
  select c.market_id, c.open_time, c.open, c.high, c.low, c.close
    from candles c, janela j
   where c.timeframe = '1m' and c.is_final
     and c.open_time >= j.ini and c.open_time < j.fim
     and c.market_id in (select id from sel)
), grade as (
  select tf, minutos from (values ('15m', 15), ('1h', 60), ('4h', 240)) as t(tf, minutos)
), dobra as (
  select g.tf, m.market_id,
         date_bin((g.minutos || ' minutes')::interval, m.open_time, timestamptz 'epoch') as bucket,
         count(*) as n,
         max(m.open_time) as ultimo,
         (array_agg(m.open  order by m.open_time))[1] as o,
         max(m.high) as h,
         min(m.low)  as l,
         (array_agg(m.close order by m.open_time desc))[1] as c,
         g.minutos
    from min1 m cross join grade g
   group by g.tf, g.minutos, m.market_id, 3
)
select sel.symbol, dobra.tf, dobra.bucket, dobra.o, dobra.h, dobra.l, dobra.c
  from dobra join sel on sel.id = dobra.market_id
 where dobra.n = dobra.minutos
   and dobra.ultimo = dobra.bucket + ((dobra.minutos - 1) || ' minutes')::interval
 order by 1, 2, 3;
commit;
