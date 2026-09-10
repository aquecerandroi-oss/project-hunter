-- T3.76 q00 -- LINHA DE BASE ANTES DO BACKFILL DE REGIME DE 90 DIAS.
-- O portao de elegibilidade da T3.52 (PIPELINE.md §4b item 10) trata hora sem
-- linha como `regime_gate:unknown`, entao uma serie que so cobre ~33 dias dos 90
-- torna TODA barra fora desses 33 dias inelegivel -- a variante com portao
-- ficaria muda na maior parte da janela e o Delta contra o pai seria medido
-- sobre nada. Esta consulta responde, e nada mais:
--   1. o que existe hoje em `market_regimes` por escopo/classificador;
--   2. horas por rotulo por mes na serie horaria (scope btc, regime_hourly_v1);
--   3. quantas horas dos ultimos 90 d tem linha e quantas faltam;
--   4. ate onde a vela de 1 min do BTC vai para tras, em HORAS COMPLETAS
--      (60 minutos is_final, a ultima em bucket+59min -- a mesma regra de
--      `regime_repo._HOURLY_CLOSES`), por mes: o insumo sem o qual o
--      classificador responde `unknown` (224 h contiguas para tendencia,
--      193 para o percentil de volatilidade);
--   5. o maior buraco contiguo dessas horas do BTC nos ultimos 130 dias
--      (`contiguous_closes` para no primeiro buraco: um buraco cega as 224 h
--      seguintes);
--   6. o universo monitorado e quantos mercados tem hora completa por mes
--      (a breadth exige cobertura de 50 % do universo).
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at, date_trunc('hour', now()) as corte;

-- 1. o que existe em market_regimes, por escopo e classificador
select scope::text,
       coalesce(classifier_version, '(null)') as classificador,
       count(*)                               as linhas,
       min(start_time)                        as primeira,
       max(start_time)                        as ultima,
       count(*) filter (where end_time is null) as abertas
  from market_regimes
 group by 1, 2
 order by 1, 2;

-- 2. serie horaria: horas por rotulo por mes
select to_char(date_trunc('month', start_time), 'YYYY-MM') as mes,
       regime::text                                        as rotulo,
       count(*)                                            as horas
  from market_regimes
 where scope = 'btc' and classifier_version = 'regime_hourly_v1'
   and start_time >= date_trunc('hour', now()) - interval '90 days'
 group by 1, 2
 order by 1, 2;

-- 3. cobertura das 2161 horas dos ultimos 90 dias
with grade as (
  select generate_series(date_trunc('hour', now()) - interval '90 days',
                         date_trunc('hour', now()), interval '1 hour') as h
), tem as (
  select distinct start_time as h
    from market_regimes
   where scope = 'btc' and classifier_version = 'regime_hourly_v1'
)
select count(*)                                as horas_da_janela,
       count(tem.h)                            as com_linha,
       count(*) - count(tem.h)                 as sem_linha,
       round(100.0 * count(tem.h) / count(*), 1) as pct_coberto
  from grade left join tem on tem.h = grade.h;

-- 4. horas COMPLETAS de vela de 1 min do BTC perpetuo, por mes, 130 dias
with btc as (
  select m.id
    from markets m join exchanges e on e.id = m.exchange_id
   where e.code = 'binance' and m.market_type = 'perpetual' and m.symbol = 'BTCUSDT'
), horas as (
  select date_bin(interval '1 hour', c.open_time, timestamptz '1970-01-01 00:00:00+00') as bucket,
         count(*) as minutos,
         max(c.open_time) as ultimo
    from candles c join btc on btc.id = c.market_id
   where c.timeframe = '1m' and c.is_final
     and c.open_time >= date_trunc('hour', now()) - interval '130 days'
     and c.open_time <  date_trunc('hour', now())
   group by 1
)
select to_char(date_trunc('month', bucket), 'YYYY-MM')                as mes,
       count(*)                                                       as horas_com_algum_minuto,
       count(*) filter (where minutos = 60 and ultimo = bucket + interval '59 minutes') as horas_completas,
       min(bucket)                                                    as primeira,
       max(bucket)                                                    as ultima
  from horas
 group by 1
 order by 1;

-- 5. o maior buraco contiguo nas horas completas do BTC (130 dias)
with btc as (
  select m.id
    from markets m join exchanges e on e.id = m.exchange_id
   where e.code = 'binance' and m.market_type = 'perpetual' and m.symbol = 'BTCUSDT'
), completas as (
  select date_bin(interval '1 hour', c.open_time, timestamptz '1970-01-01 00:00:00+00') as bucket
    from candles c join btc on btc.id = c.market_id
   where c.timeframe = '1m' and c.is_final
     and c.open_time >= date_trunc('hour', now()) - interval '130 days'
     and c.open_time <  date_trunc('hour', now())
   group by 1
  having count(*) = 60
     and max(c.open_time) = date_bin(interval '1 hour', c.open_time, timestamptz '1970-01-01 00:00:00+00') + interval '59 minutes'
), lag_ as (
  select bucket, lag(bucket) over (order by bucket) as anterior from completas
)
select count(*)                                                as buracos,
       coalesce(max(extract(epoch from (bucket - anterior))/3600 - 1), 0) as maior_buraco_horas,
       min(bucket) filter (where bucket - anterior > interval '1 hour') as primeiro_buraco_em
  from lag_
 where anterior is not null and bucket - anterior > interval '1 hour';

-- 6. universo monitorado e cobertura de hora completa por mes
with uni as (
  select m.id, m.symbol
    from markets m join exchanges e on e.id = m.exchange_id
   where e.code = 'binance' and m.market_type = 'perpetual' and m.is_monitored
), horas as (
  select c.market_id,
         date_bin(interval '1 hour', c.open_time, timestamptz '1970-01-01 00:00:00+00') as bucket,
         count(*) as minutos
    from candles c join uni on uni.id = c.market_id
   where c.timeframe = '1m' and c.is_final
     and c.open_time >= date_trunc('hour', now()) - interval '100 days'
     and c.open_time <  date_trunc('hour', now())
   group by 1, 2
  having count(*) = 60
)
select (select count(*) from uni)                                as universo_monitorado,
       to_char(date_trunc('month', bucket), 'YYYY-MM')           as mes,
       count(distinct market_id)                                 as mercados_com_hora_completa,
       count(*)                                                  as horas_mercado
  from horas
 group by 2
 order by 2;

commit;
