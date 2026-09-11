-- D-P19 q00 — catálogo e cortes (somente leitura)
-- A meta de R$ 9.000/dia em DINHEIRO: quem é o universo, quanto dado existe, qual é o câmbio.
-- Uso: ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter -v ON_ERROR_STOP=1 -f -" < este arquivo
begin transaction isolation level repeatable read read only;

\echo '== 0. corte da leitura (UTC e Brasília) =='
select now() as as_of_utc,
       (now() at time zone 'America/Sao_Paulo') as as_of_brt;

\echo '== 1. os 16 mercados, perpétuo e o gêmeo SPOT =='
select m.symbol,
       m.market_type::text as tipo,
       m.is_monitored,
       m.status::text,
       round(m.volume_24h_usd / 1e6, 2) as vol24h_musd,
       (m.volume_24h_usd >= 50000000) as passa_piso_50m,
       m.min_notional,
       m.step_size,
       m.id::text as market_id
  from markets m
  join exchanges e on e.id = m.exchange_id
 where e.code = 'binance'
   and m.symbol in ('ARBUSDT','BNBUSDT','BTCUSDT','DASHUSDT','DOGEUSDT','ETHUSDT','LINKUSDT',
                    'NEARUSDT','PROMUSDT','SAHARAUSDT','SOLUSDT','SUIUSDT','TAOUSDT','UNIUSDT',
                    'XRPUSDT','ZECUSDT')
 order by m.symbol, m.market_type::text;

\echo '== 2. cobertura de candles_1m nos últimos 30 dias =='
select m.symbol,
       m.market_type::text as tipo,
       count(*) as barras,
       round(100.0 * count(*) / 43200, 2) as pct_de_30d,
       min(c.open_time) as primeira,
       max(c.open_time) as ultima
  from candles_1m c
  join markets m on m.id = c.market_id
  join exchanges e on e.id = m.exchange_id
 where e.code = 'binance'
   and c.open_time >= now() - interval '30 days'
   and m.symbol in ('ARBUSDT','BNBUSDT','BTCUSDT','DASHUSDT','DOGEUSDT','ETHUSDT','LINKUSDT',
                    'NEARUSDT','PROMUSDT','SAHARAUSDT','SOLUSDT','SUIUSDT','TAOUSDT','UNIUSDT',
                    'XRPUSDT','ZECUSDT')
 group by 1, 2
 order by 1, 2;

\echo '== 3. câmbio USDT/BRL mais recente =='
select pair, rate, source, observed_at,
       (observed_at at time zone 'America/Sao_Paulo') as observed_at_brt
  from fx_observations
 where pair = 'USDTBRL'
 order by observed_at desc
 limit 1;

\echo '== 4. a família viva e os desfechos disponíveis =='
select s.key, sv.version, sv.status::text, sv.purpose, sv.activated_at, sv.deprecated_at
  from strategy_versions sv
  join strategies s on s.id = sv.strategy_id
 where s.key like 'mean_reversion%'
 order by sv.activated_at nulls last, s.key, sv.version;

\echo '== 5. desfechos prospectivos terminais da família nos últimos 30 dias =='
select s.key,
       count(*) as desfechos,
       count(*) filter (where so.r_multiple is not null) as com_r,
       min(so.entry_ts) as primeiro,
       max(so.entry_ts) as ultimo
  from signal_outcomes so
  join agent_signals sig on sig.id = so.signal_id
  join strategy_versions sv on sv.id = sig.strategy_version_id
  join strategies s on s.id = sv.strategy_id
 where so.meta->>'cohort' = 'prospective'
   and so.tracking_state = 'terminal'
   and so.entry_ts >= now() - interval '30 days'
   and s.key like 'mean_reversion%'
 group by 1
 order by 1;

commit;
