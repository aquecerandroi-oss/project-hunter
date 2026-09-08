-- T3.46 — as mesmas duas populacoes da consulta 03 (evento de anomalia e barra
-- de base pareada) exportadas em CSV para o bootstrap por blocos de hora.
--
-- SOMENTE LEITURA. Uma linha por observacao:
--   grupo  'anomalia' | 'base'
--   hora   hora UTC da observacao (bloco do bootstrap)
--   symbol mercado (o pareamento e por mercado)
--   ret60/ret240  retorno ate +60 min / +240 min sobre velas 1m is_final
--
-- A base exclui todo minuto com anomalia detectada nos 60 minutos anteriores ou
-- no proprio minuto — a mesma regra da consulta 03.
select 'anomalia' as grupo,
       to_char(date_trunc('hour', a.detected_at), 'YYYY-MM-DD HH24') as hora,
       m.symbol,
       round(c1.close / c0.close - 1, 8) as ret60,
       round(c4.close / c0.close - 1, 8) as ret240
  from anomalies a
  join markets m on m.id = a.market_id
  join candles c0 on c0.market_id = a.market_id and c0.timeframe = '1m'
                 and c0.is_final and c0.open_time = date_trunc('minute', a.detected_at)
  left join candles c1 on c1.market_id = a.market_id and c1.timeframe = '1m'
                 and c1.is_final and c1.open_time = date_trunc('minute', a.detected_at) + interval '60 minutes'
  left join candles c4 on c4.market_id = a.market_id and c4.timeframe = '1m'
                 and c4.is_final and c4.open_time = date_trunc('minute', a.detected_at) + interval '240 minutes'
union all
select 'base',
       to_char(date_trunc('hour', c.open_time), 'YYYY-MM-DD HH24'),
       m.symbol,
       round(c1.close / c.close - 1, 8),
       round(c4.close / c.close - 1, 8)
  from candles c
  join (select distinct market_id from anomalies) mk on mk.market_id = c.market_id
  join markets m on m.id = c.market_id
  left join candles c1 on c1.market_id = c.market_id and c1.timeframe = '1m'
                 and c1.is_final and c1.open_time = c.open_time + interval '60 minutes'
  left join candles c4 on c4.market_id = c.market_id and c4.timeframe = '1m'
                 and c4.is_final and c4.open_time = c.open_time + interval '240 minutes'
 where c.timeframe = '1m' and c.is_final
   and c.open_time >= (select date_trunc('minute', min(detected_at)) from anomalies)
   and c.open_time <= (select date_trunc('minute', max(detected_at)) from anomalies)
   and not exists (select 1 from anomalies an
                    where an.market_id = c.market_id
                      and an.detected_at <= c.open_time + interval '1 minute'
                      and an.detected_at >  c.open_time - interval '60 minutes');
