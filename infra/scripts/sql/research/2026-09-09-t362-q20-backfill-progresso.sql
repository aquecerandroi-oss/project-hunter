-- T3.62 q20 — como acompanhar o backfill de 90 d dos 16 mercados: a fila da
-- outbox, as lacunas por estado e por mercado, e a profundidade real
-- (min(open_time) por mercado), que e o numero que decide quando um replay de
-- 90 d passa a ser possivel. SOMENTE LEITURA. Rode de tempos em tempos.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

\echo '--- 1. outbox: quantos pedidos ainda nao foram despachados ---'
select count(*) filter (where dispatched_at is null) as pendentes,
       count(*) filter (where dispatched_at is not null) as despachados,
       min(created_at) as mais_antigo, max(created_at) as mais_novo
  from outbox_events
 where stream = 'market.backfill.requested'
   and created_at >= timestamptz '2026-09-09 20:20:00+00';

\echo '--- 2. lacunas por mercado e estado (as abertas sao o trabalho restante) ---'
select m.symbol, g.status, count(*) as pedacos,
       min(g.gap_start) as mais_antigo, max(g.gap_end) as mais_novo
  from ingestion_gaps g
  join markets m on m.id = g.market_id
 where g.detected_at > timestamptz '2026-09-09 20:20:00+00'
 group by 1, 2
 order by 1, 2;

\echo '--- 3. profundidade real por mercado (o numero que libera o replay de 90 d) ---'
with alvo(symbol) as (
  values ('BTCUSDT'),('ETHUSDT'),('ZECUSDT'),('SOLUSDT'),('XRPUSDT'),('BNBUSDT'),
         ('DOGEUSDT'),('SUIUSDT'),('NEARUSDT'),('UNIUSDT'),('ARBUSDT'),('TAOUSDT'),
         ('LINKUSDT'),('DASHUSDT'),('PROMUSDT'),('SAHARAUSDT')
)
select m.symbol,
       min(c.open_time) as primeira_vela,
       max(c.open_time) as ultima_vela,
       count(*) as minutos,
       round(extract(epoch from (max(c.open_time) - min(c.open_time)))/86400.0, 2) as alcance_dias,
       round(100.0 * count(*) / nullif(extract(epoch from (max(c.open_time) - min(c.open_time)))/60.0, 0), 2) as densidade_pct
  from candles c
  join markets m on m.id = c.market_id
  join exchanges e on e.id = m.exchange_id
 where c.timeframe = '1m' and c.is_final
   and e.code = 'binance' and m.market_type = 'perpetual'
   and m.symbol in (select symbol from alvo)
 group by 1
 order by 2, 1;

\echo '--- 4. lacunas irrecuperaveis (esperado logo apos um lote; deve estabilizar) ---'
select m.symbol, count(*) as lacunas, min(g.gap_start) as mais_antigo, max(g.gap_end) as mais_novo
  from ingestion_gaps g
  join markets m on m.id = g.market_id
 where g.status = 'unrecoverable'
 group by 1 order by 2 desc limit 20;
commit;
