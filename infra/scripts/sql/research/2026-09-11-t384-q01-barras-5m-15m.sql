-- T3.84 q01 (EXP-0028, previsao P1) -- as velas de 5 m e de 15 m dos 16 mercados
-- elegiveis, na MESMA janela de 31 d que a T3.54 mediu (2026-08-08 -> 2026-09-08)
-- e com o MESMO metodo: dobra no servidor com exigencia de completude (apenas
-- `is_final`, `count(*) = n_minutos` e o ultimo minuto exatamente em
-- `bucket + n-1 min`, a regra de `beta_repo.bar_closes` / PIPELINE 2b item 2).
--
-- Por que a mesma janela: P1 da EXP-0028 e uma EXTRAPOLACAO da medicao da T3.54
-- (ATR%(15m) p50 = 0,5585 % naqueles 31 dias, expoente H = ln(2,208)/ln(4)).
-- Medir 5 m em outra janela mediria duas coisas ao mesmo tempo. O 15 m sai junto
-- como controle de metodo: se a conta aqui nao reproduzir 0,5585 %, o numero de
-- 5 m tambem nao vale.
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
