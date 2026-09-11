-- T3.86 q00 — `markets.volume_24h_usd` (foto do ticker) contra o volume de 24 h somado das velas.
-- SOMENTE LEITURA. Uso:
--   ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter -v ON_ERROR_STOP=1 -f -" < este arquivo
-- Pergunta: o insumo do check 9 (`liquidity_24h`, piso de 50 M) e o carimbo que o motor usa
-- (`volume_ts`, fim do ultimo minuto completo) descrevem o mesmo mercado e o mesmo instante?
begin transaction isolation level repeatable read read only;

\echo '== 0. corte da leitura =='
select now() as as_of_utc, (now() at time zone 'America/Sao_Paulo') as as_of_brt,
       date_trunc('minute', now()) as t_minuto;

\echo '== 1. a coluna de carimbo que existe em markets =='
select column_name, data_type
  from information_schema.columns
 where table_name = 'markets' and (column_name like '%_at' or column_name like '%volume%')
 order by ordinal_position;

\echo '== 2. 24 h: ticker (markets.volume_24h_usd) x velas (soma de candles_1m), por mercado =='
with corte as (select date_trunc('minute', now()) as t),
universo as (
  select m.id, m.symbol, m.market_type::text as tipo, m.is_monitored, m.status::text as status,
         m.volume_24h_usd, m.last_seen_at
    from markets m
    join exchanges e on e.id = m.exchange_id
   where e.code = 'binance'
     and (
       (m.market_type = 'spot' and m.is_monitored and m.status = 'active' and m.delisted_at is null)
       or m.symbol in ('ARBUSDT','BNBUSDT','BTCUSDT','DASHUSDT','DOGEUSDT','ETHUSDT','LINKUSDT',
                       'NEARUSDT','PROMUSDT','SAHARAUSDT','SOLUSDT','SUIUSDT','TAOUSDT','UNIUSDT',
                       'XRPUSDT','ZECUSDT')
     )
),
velas as (
  select u.id,
         sum(c.quote_volume) filter (where c.is_final) as vol24h_velas,
         count(*) filter (where c.is_final) as minutos,
         max(c.open_time) filter (where c.is_final) as ultima_vela
    from universo u
    left join candles_1m c
      on c.market_id = u.id
     and c.open_time >= (select t from corte) - interval '24 hours'
     and c.open_time <  (select t from corte)
   group by u.id
)
select u.symbol, u.tipo, u.is_monitored as monit,
       round(u.volume_24h_usd / 1e6, 2) as ticker_musd,
       round(v.vol24h_velas / 1e6, 2) as velas_musd,
       round(v.vol24h_velas / nullif(u.volume_24h_usd, 0), 2) as razao_velas_ticker,
       v.minutos,
       round(extract(epoch from ((select t from corte) - u.last_seen_at)))::int as last_seen_age_s,
       round(extract(epoch from ((select t from corte) - (v.ultima_vela + interval '1 minute'))))::int
         as vela_age_s,
       (u.volume_24h_usd >= 50000000) as passa_piso_ticker,
       (v.vol24h_velas >= 50000000) as passa_piso_velas
  from universo u
  join velas v on v.id = u.id
 order by u.tipo, u.symbol;

\echo '== 3. divergencias de veredito: o piso de 50 M discorda entre as duas fontes =='
with corte as (select date_trunc('minute', now()) as t),
universo as (
  select m.id, m.symbol, m.market_type::text as tipo, m.volume_24h_usd
    from markets m
    join exchanges e on e.id = m.exchange_id
   where e.code = 'binance'
     and ((m.market_type = 'spot' and m.is_monitored and m.status = 'active' and m.delisted_at is null)
          or m.symbol in ('ARBUSDT','BNBUSDT','BTCUSDT','DASHUSDT','DOGEUSDT','ETHUSDT','LINKUSDT',
                          'NEARUSDT','PROMUSDT','SAHARAUSDT','SOLUSDT','SUIUSDT','TAOUSDT','UNIUSDT',
                          'XRPUSDT','ZECUSDT'))
),
velas as (
  select u.id, sum(c.quote_volume) filter (where c.is_final) as vol24h_velas
    from universo u
    left join candles_1m c
      on c.market_id = u.id
     and c.open_time >= (select t from corte) - interval '24 hours'
     and c.open_time <  (select t from corte)
   group by u.id
)
select u.symbol, u.tipo,
       round(u.volume_24h_usd / 1e6, 2) as ticker_musd,
       round(v.vol24h_velas / 1e6, 2) as velas_musd,
       case when u.volume_24h_usd >= 50000000 then 'passa' else 'reprova' end as veredito_ticker,
       case when v.vol24h_velas >= 50000000 then 'passa' else 'reprova' end as veredito_velas
  from universo u
  join velas v on v.id = u.id
 where (u.volume_24h_usd >= 50000000) is distinct from (v.vol24h_velas >= 50000000)
 order by u.tipo, u.symbol;

\echo '== 4. idade do ticker na pratica: distancia entre last_seen_at e agora, por tipo =='
select m.market_type::text as tipo,
       count(*) as linhas,
       round(extract(epoch from (now() - min(m.last_seen_at))))::int as mais_velho_s,
       round(extract(epoch from (now() - max(m.last_seen_at))))::int as mais_novo_s
  from markets m join exchanges e on e.id = m.exchange_id
 where e.code = 'binance' and m.is_monitored
 group by 1 order by 1;

commit;
