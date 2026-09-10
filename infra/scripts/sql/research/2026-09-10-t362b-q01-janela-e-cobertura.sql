-- T3.62b q01 -- A JANELA LIMPA DE VERDADE, e se ela aguenta os TRES recortes de ~30 d.
-- O agente anterior escolheu 2026-06-12 -> 2026-09-10 (3 x 30 d) para a v10. Antes
-- de medir qualquer coisa em cima disso eu preciso saber se a fita e do mesmo
-- material nos tres recortes: um junho com 80 % de vela e um agosto com 100 %
-- produziriam uma diferenca de regime que e, na verdade, uma diferenca de dado.
-- Tres leituras:
--   1. profundidade bruta por mercado (min/max e minutos finais na janela);
--   2. densidade por recorte de 30 d (o numero que decide se os tres comparam);
--   3. os dias com buraco, mercado a mercado, para que "limpa" seja verificavel.
-- Bar-features so leem is_final = true (PIPELINE SS2): a contagem e sobre is_final.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

-- 1. profundidade bruta por mercado dentro da janela
with mkt as (
  select m.id, m.symbol
    from markets m
    join exchanges e on e.id = m.exchange_id
   where e.code = 'binance' and m.market_type = 'perpetual'
     and m.symbol in ('BTCUSDT','ETHUSDT','ZECUSDT','SOLUSDT','XRPUSDT','BNBUSDT',
                      'DOGEUSDT','SUIUSDT','NEARUSDT','UNIUSDT','ARBUSDT','TAOUSDT',
                      'LINKUSDT','DASHUSDT','PROMUSDT','SAHARAUSDT')
)
select k.symbol,
       min(c.open_time) as primeira_vela,
       max(c.open_time) as ultima_vela,
       count(*)         as minutos_finais,
       round(100.0 * count(*) / (90*1440), 2) as densidade_pct
  from candles c
  join mkt k on k.id = c.market_id
 where c.timeframe = '1m' and c.is_final
   and c.open_time >= timestamptz '2026-06-12 00:00+00'
   and c.open_time <  timestamptz '2026-09-10 00:00+00'
 group by 1
 order by 2, 1;

-- 2. densidade por recorte de 30 d (os tres meses do brief)
with mkt as (
  select m.id, m.symbol
    from markets m
    join exchanges e on e.id = m.exchange_id
   where e.code = 'binance' and m.market_type = 'perpetual'
     and m.symbol in ('BTCUSDT','ETHUSDT','ZECUSDT','SOLUSDT','XRPUSDT','BNBUSDT',
                      'DOGEUSDT','SUIUSDT','NEARUSDT','UNIUSDT','ARBUSDT','TAOUSDT',
                      'LINKUSDT','DASHUSDT','PROMUSDT','SAHARAUSDT')
), jan as (
  select 'J1 06-12->07-12' as janela, timestamptz '2026-06-12 00:00+00' as de, timestamptz '2026-07-12 00:00+00' as ate
  union all select 'J2 07-12->08-11', timestamptz '2026-07-12 00:00+00', timestamptz '2026-08-11 00:00+00'
  union all select 'J3 08-11->09-10', timestamptz '2026-08-11 00:00+00', timestamptz '2026-09-10 00:00+00'
)
select j.janela,
       count(distinct c.market_id)                              as mercados,
       count(*)                                                 as minutos_finais,
       16 * 30 * 1440                                           as minutos_esperados,
       round(100.0 * count(*) / (16*30*1440), 2)                as densidade_pct,
       min(c.open_time)                                         as primeiro,
       max(c.open_time)                                         as ultimo
  from jan j
  join candles c on c.timeframe = '1m' and c.is_final
                and c.open_time >= j.de and c.open_time < j.ate
  join mkt k on k.id = c.market_id
 group by 1
 order by 1;

-- 3. dias incompletos (< 1440 min finais), mercado a mercado
with mkt as (
  select m.id, m.symbol
    from markets m
    join exchanges e on e.id = m.exchange_id
   where e.code = 'binance' and m.market_type = 'perpetual'
     and m.symbol in ('BTCUSDT','ETHUSDT','ZECUSDT','SOLUSDT','XRPUSDT','BNBUSDT',
                      'DOGEUSDT','SUIUSDT','NEARUSDT','UNIUSDT','ARBUSDT','TAOUSDT',
                      'LINKUSDT','DASHUSDT','PROMUSDT','SAHARAUSDT')
), dia as (
  select (c.open_time at time zone 'UTC')::date as dia, k.symbol, count(*) as minutos
    from candles c
    join mkt k on k.id = c.market_id
   where c.timeframe = '1m' and c.is_final
     and c.open_time >= timestamptz '2026-06-12 00:00+00'
     and c.open_time <  timestamptz '2026-09-10 00:00+00'
   group by 1, 2
)
select dia, count(*) as mercados_furados, sum(1440 - minutos) as minutos_faltando,
       string_agg(symbol || ':' || (1440 - minutos), ' ' order by symbol) as detalhe
  from dia
 where minutos <> 1440
 group by 1
 order by 1;

commit;
