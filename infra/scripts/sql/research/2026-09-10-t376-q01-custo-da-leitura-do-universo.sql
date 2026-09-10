-- T3.76 q01 -- QUANTO CUSTA A FASE DE LEITURA DE UMA PASSADA DE 90 DIAS.
-- `regime_job._read_inputs` le o universo inteiro (`regime_repo.hourly_closes`,
-- lotes de 25 mercados) de `earliest - 25 h` ate o corte. Com `--repair-days 90`
-- o `earliest` e o corte menos 90 dias, entao a leitura passa a varrer ~90 d de
-- velas de 1 min de 200 mercados numa VPS de um core. Antes de rodar a passada
-- (que ESCREVE) e barato medir a metade que so LE: um lote de 25 mercados, a
-- consulta identica a de producao, com \timing.
-- Se um lote custa T, a fase de leitura do universo custa ~8*T e a passada
-- inteira nao cabe em `timeout 290` se 8*T passar de ~200 s.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\timing on
select now() as read_at;

-- um lote de 25 mercados monitorados (os mesmos ids, na mesma ordem que o job
-- usaria: `MarketRegistry` ordena por symbol), 90 dias + 25 h de folga
with uni as (
  select m.id
    from markets m join exchanges e on e.id = m.exchange_id
   where e.code = 'binance' and m.market_type = 'perpetual' and m.is_monitored
   order by m.symbol
   limit 25
), bars as (
  select c.market_id,
         date_bin(interval '1 hour', c.open_time, timestamptz '1970-01-01 00:00:00+00') as bucket,
         count(*) as minutes,
         max(c.open_time) as last_minute,
         (array_agg(c.close order by c.open_time desc))[1] as close
    from candles c join uni on uni.id = c.market_id
   where c.timeframe = '1m' and c.is_final
     and c.open_time >= date_trunc('hour', now()) - interval '90 days' - interval '25 hours'
     and c.open_time <  date_trunc('hour', now())
   group by 1, 2
)
select count(*) as horas_completas, count(distinct market_id) as mercados
  from bars
 where minutes = 60 and last_minute = bucket + interval '59 minutes';

-- a leitura da referencia (BTC), 90 d + 745 h de profundidade
with btc as (
  select m.id from markets m join exchanges e on e.id = m.exchange_id
   where e.code = 'binance' and m.market_type = 'perpetual' and m.symbol = 'BTCUSDT'
), bars as (
  select date_bin(interval '1 hour', c.open_time, timestamptz '1970-01-01 00:00:00+00') as bucket,
         count(*) as minutes,
         max(c.open_time) as last_minute
    from candles c join btc on btc.id = c.market_id
   where c.timeframe = '1m' and c.is_final
     and c.open_time >= date_trunc('hour', now()) - interval '90 days' - interval '745 hours'
     and c.open_time <  date_trunc('hour', now())
   group by 1
)
select count(*) as horas_completas_btc
  from bars where minutes = 60 and last_minute = bucket + interval '59 minutes';

commit;
