-- D-P9 q08 -- EM QUE MINUTO EXATO AS POSICOES MORRERAM.
-- A amplitude do q05 mostrou um minuto excepcional: 22:08Z (19:08 BRT), com 194
-- dos 200 perpetuos monitorados caindo, media -3,71 % e mediana -1,76 % em UM
-- minuto, e o BTC caindo so -0,204 % (volume 1425 BTC contra ~50 tipicos).
-- Aqui: quantas das saidas caem nesse minuto -- na hora 21Z e no dia inteiro.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off

-- 1. histograma do minuto de saida das 39 decisoes das 21Z
with pop as (
  select mk.symbol, s.key || ' ' || sv.version as versao, o.exit_ts,
         o.result::text as saida, o.r_multiple as r_net
    from signal_outcomes o
    join agent_signals a      on a.id = o.signal_id
    join markets mk           on mk.id = a.market_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
   where o.meta->>'cohort' = 'prospective'
     and ( (s.key = 'mean_reversion' and sv.version in ('v1','v2','v3','v6','v7','v8','v10','v14'))
        or (s.key = 'mean_reversion_h1' and sv.version = 'v1') )
     and o.tracking_state = 'terminal'
     and a.emitted_at >= '2026-09-09 21:00:00+00' and a.emitted_at < '2026-09-09 22:00:00+00'
)
select to_char(exit_ts at time zone 'America/Sao_Paulo','HH24:MI') minuto_brt,
       to_char(exit_ts at time zone 'UTC','HH24:MI') minuto_utc,
       count(*) n, string_agg(distinct symbol, ',') mercados,
       count(*) filter (where saida='stop') stops,
       count(*) filter (where saida='expired') tempo,
       round(sum(r_net),3) soma_r
  from pop group by 1,2 order by 2;

-- 2. o dia 09/09 BRT inteiro: os 12 minutos de saida mais caros
with pop as (
  select mk.symbol, o.exit_ts, o.result::text as saida, o.r_multiple as r_net
    from signal_outcomes o
    join agent_signals a      on a.id = o.signal_id
    join markets mk           on mk.id = a.market_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
   where o.meta->>'cohort' = 'prospective'
     and ( (s.key = 'mean_reversion' and sv.version in ('v1','v2','v3','v6','v7','v8','v10','v14'))
        or (s.key = 'mean_reversion_h1' and sv.version = 'v1') )
     and o.tracking_state = 'terminal'
     and (a.emitted_at at time zone 'America/Sao_Paulo')::date = date '2026-09-09'
)
select to_char(exit_ts at time zone 'America/Sao_Paulo','DD/MM HH24:MI') minuto_brt,
       to_char(exit_ts at time zone 'UTC','DD/MM HH24:MI') minuto_utc,
       count(*) n, count(distinct symbol) mercados,
       count(*) filter (where saida='stop') stops,
       round(sum(r_net),3) soma_r
  from pop group by 1,2 order by 6 limit 12;

-- 3. e a queda do universo naquele minuto, por mercado (os 15 piores de 22:08Z)
with universo as (
  select m.id, m.symbol from markets m
   where m.market_type = 'perpetual' and m.is_monitored
)
select u.symbol, c.open, c.close,
       round(100*(c.close - c.open)/c.open, 3) ret_pct,
       round(100*(c.low - c.open)/c.open, 3) ate_a_minima_pct,
       c.volume, c.trade_count
  from candles_1m c join universo u on u.id = c.market_id
 where c.is_final and c.open_time = '2026-09-09 22:08:00+00'
 order by 4 limit 15;

commit;
