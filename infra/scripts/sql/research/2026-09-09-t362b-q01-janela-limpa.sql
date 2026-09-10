-- T3.62b q01 -- QUAL E A JANELA LIMPA, de verdade, depois do backfill de 90 d.
-- Tres perguntas, nesta ordem, porque a terceira e a que decide o --from do replay:
--   1. min/max(open_time) por mercado -- a profundidade bruta;
--   2. por dia UTC, quantos dos 16 mercados fecharam o dia com os 1440 minutos
--      finais (a regra de completude do brief) -- o piso da janela limpa;
--   3. os dias incompletos, com quem falhou e quanto, para que "limpa" seja uma
--      afirmacao verificavel e nao um voto.
-- Sem tabela temporaria: `repeatable read read only` recusa CREATE TABLE AS, e a
-- transacao read only e a garantia que o brief pede -- entao CTE em cada consulta.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

-- 1. profundidade bruta por mercado
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
       count(*)         as minutos_finais
  from candles c
  join mkt k on k.id = c.market_id
 where c.timeframe = '1m' and c.is_final
 group by 1
 order by 2, 1;

-- 2. completude por dia UTC
with mkt as (
  select m.id, m.symbol
    from markets m
    join exchanges e on e.id = m.exchange_id
   where e.code = 'binance' and m.market_type = 'perpetual'
     and m.symbol in ('BTCUSDT','ETHUSDT','ZECUSDT','SOLUSDT','XRPUSDT','BNBUSDT',
                      'DOGEUSDT','SUIUSDT','NEARUSDT','UNIUSDT','ARBUSDT','TAOUSDT',
                      'LINKUSDT','DASHUSDT','PROMUSDT','SAHARAUSDT')
), dia as (
  select (c.open_time at time zone 'UTC')::date as dia, c.market_id, count(*) as minutos
    from candles c
    join mkt k on k.id = c.market_id
   where c.timeframe = '1m' and c.is_final
   group by 1, 2
)
select dia,
       count(*) filter (where minutos = 1440) as completos_1440,
       count(*)                               as mercados_com_algum,
       min(minutos)                           as pior_mercado,
       sum(1440 - minutos)                    as minutos_faltando
  from dia
 group by 1
 order by 1;

-- 3. os dias incompletos, mercado a mercado (so o que falta)
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
   group by 1, 2
)
select dia, symbol, minutos, 1440 - minutos as faltam
  from dia
 where minutos <> 1440
 order by dia, symbol;

commit;
