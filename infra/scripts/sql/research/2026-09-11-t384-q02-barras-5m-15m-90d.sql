-- T3.84 q02 (EXP-0028) -- as MESMAS velas de 5 m e de 15 m dos 16 mercados, na
-- JANELA PROPRIA DO EXPERIMENTO: 90 dias, 2026-06-12 -> 2026-09-10 (as tres
-- janelas de 30 d da EXP-0025 emendadas). Mesmo metodo da q01 (dobra no servidor
-- com exigencia de completude: apenas `is_final`, `count(*) = n_minutos` e o
-- ultimo minuto exatamente em `bucket + n-1 min` -- a regra de
-- `beta_repo.bar_closes` / PIPELINE 2b item 2).
--
-- A q01 mede na janela de 31 d da T3.54 porque e de la que a previsao P1 foi
-- extrapolada (comparacao pareada). Esta mede na janela em que a versao seria
-- avaliada, para que a fracao de barras que passa o piso `atr_pct_min = 0,006`
-- e o pedagio condicional sejam os do experimento, e nao os de outro mes.
--
-- O Wilder ATR-14 e calculado FORA daqui, pelo mesmo
-- `hunter_core.strategies.indicators.wilder_atr` que `mean_reversion_m5_v1`
-- chama, sobre janelas rolantes de `atr_bars = 97` -- reimplementar Wilder em
-- SQL seria um segundo calculo com liberdade para discordar do que decide.
-- Saida CSV no stdout. SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset format csv
\pset tuples_only off

with janela as (
  select timestamptz '2026-06-12 00:00:00+00' as ini,
         timestamptz '2026-09-10 00:00:00+00' as fim
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
  select tf, minutos from (values ('5m', 5), ('15m', 15)) as t(tf, minutos)
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
