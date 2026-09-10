-- D-P9 q05 -- O BTC NO MESMO MINUTO E O ROTULO DO REGIME DA HORA ANTERIOR.
-- Tres leituras:
--   1. BTCUSDT perpetuo, 1 min, 20:45Z-23:15Z de 09/09 (17:45-20:15 BRT), com
--      retorno por minuto e acumulado desde 21:00Z;
--   2. `market_regimes` do classificador horario `regime_hourly_v1` (T3.43,
--      docs/PIPELINE.md 4b): a linha da hora `ts` foi decidida com velas
--      fechadas ANTES de `ts`, entao a linha que vale para uma decisao das
--      21:0xZ e a de `ts = 21:00Z` -- e a "hora anterior fechada" e a de 20:00Z;
--   3. AMPLITUDE (breadth): fracao dos perpetuos monitorados que caiu em cada
--      minuto da janela -- e o teste de "queda comum" contra "azar de 7 mercados".
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off

-- 1. BTC perpetuo minuto a minuto
with btc as (
  select c.open_time, c.open, c.high, c.low, c.close, c.volume, c.trade_count
    from candles_1m c
    join markets m on m.id = c.market_id
    join exchanges e on e.id = m.exchange_id
   where m.symbol = 'BTCUSDT' and m.market_type = 'perpetual' and e.code = 'binance'
     and c.is_final
     and c.open_time >= '2026-09-09 20:45:00+00' and c.open_time < '2026-09-09 23:15:00+00'
), base as (
  select (select close from btc where open_time = '2026-09-09 20:59:00+00') as ref
)
select to_char(open_time at time zone 'America/Sao_Paulo','HH24:MI') minuto_brt,
       to_char(open_time at time zone 'UTC','HH24:MI') minuto_utc,
       close, round(100*(close - open)/open, 3) as ret_min_pct,
       round(100*(high - low)/open, 3) as amplitude_pct,
       round(100*(close - (select ref from base))/(select ref from base), 3) as desde_2100z_pct,
       volume, trade_count
  from btc order by open_time;

-- 2. resumo do BTC por hora na janela
with btc as (
  select c.open_time, c.open, c.high, c.low, c.close
    from candles_1m c
    join markets m on m.id = c.market_id
    join exchanges e on e.id = m.exchange_id
   where m.symbol = 'BTCUSDT' and m.market_type = 'perpetual' and e.code = 'binance'
     and c.is_final
     and c.open_time >= '2026-09-09 18:00:00+00' and c.open_time < '2026-09-10 03:00:00+00'
)
select to_char(date_trunc('hour', open_time) at time zone 'UTC','DD/MM HH24:MI') hora_utc,
       to_char(date_trunc('hour', open_time) at time zone 'America/Sao_Paulo','HH24:MI') hora_brt,
       count(*) minutos,
       (array_agg(open order by open_time))[1] abertura,
       max(high) maxima, min(low) minima,
       (array_agg(close order by open_time desc))[1] fechamento,
       round(100*(((array_agg(close order by open_time desc))[1]) - ((array_agg(open order by open_time))[1]))
             / ((array_agg(open order by open_time))[1]), 3) as var_hora_pct
  from btc group by 1,2 order by 1;

-- 3. regime horario (todas as versoes/escopos gravados na janela)
select id, scope::text, regime::text, classifier_version, confidence,
       to_char(start_time at time zone 'UTC','DD/MM HH24:MI') inicio_utc,
       to_char(start_time at time zone 'America/Sao_Paulo','DD/MM HH24:MI') inicio_brt,
       to_char(end_time at time zone 'UTC','DD/MM HH24:MI') fim_utc,
       supporting_features
  from market_regimes
 where start_time >= '2026-09-09 16:00:00+00' and start_time < '2026-09-10 02:00:00+00'
 order by classifier_version, start_time;

-- 4. amplitude: quantos perpetuos monitorados caem em cada minuto da janela
with universo as (
  select m.id from markets m
   where m.market_type = 'perpetual' and m.is_monitored
), velas as (
  select c.open_time, c.market_id,
         case when c.close < c.open then 1 else 0 end as caiu,
         (c.close - c.open)/nullif(c.open,0) as ret
    from candles_1m c
    join universo u on u.id = c.market_id
   where c.is_final
     and c.open_time >= '2026-09-09 20:55:00+00' and c.open_time < '2026-09-09 22:20:00+00'
)
select to_char(open_time at time zone 'America/Sao_Paulo','HH24:MI') minuto_brt,
       to_char(open_time at time zone 'UTC','HH24:MI') minuto_utc,
       count(*) mercados, sum(caiu) caindo,
       round(100.0*sum(caiu)/count(*),1) pct_caindo,
       round(100*avg(ret),4) ret_medio_pct,
       round(100*percentile_cont(0.5) within group (order by ret)::numeric,4) ret_mediano_pct
  from velas group by 1,2 order by 2;

commit;
