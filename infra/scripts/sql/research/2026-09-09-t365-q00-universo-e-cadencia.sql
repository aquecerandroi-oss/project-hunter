-- T3.65 q00 — dos nove perpétuos TradFi que a Binance moveu de 8h para 4h de
-- funding em 2026-09-04 08:15Z, quais estão no nosso universo monitorado e
-- qual a contagem de settlements/dia antes e depois da mudança. SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;

select now() as read_at;

-- 1. Quais dos nove símbolos existem em `markets`, e são monitorados hoje?
select m.symbol, e.code as exchange, m.status, m.is_monitored, m.monitor_rank,
       m.first_seen_at, m.delisted_at
  from markets m
  join exchanges e on e.id = m.exchange_id
 where m.symbol in (
   'KODEX200USDT','NAVERUSDT','LGELECTRONICSUSDT','HANMIUSDT','SAMSUNGELUSDT',
   'CXMTUSDT','ZHONGJIUSDT','CSOPSAMSUNG2LUSDT','CSOPSKHYNIX2LUSDT'
 )
 order by m.symbol;

-- 2. Para os que existem: settlements por dia, últimos 12 dias (a transição
--    foi 2026-09-04; isto cobre antes e depois).
select m.symbol,
       date_trunc('day', fr.funding_time) as dia,
       count(*) as settlements_no_dia,
       min(fr.funding_time) as primeiro,
       max(fr.funding_time) as ultimo
  from funding_rates fr
  join markets m on m.id = fr.market_id
  join exchanges e on e.id = m.exchange_id
 where m.symbol in (
   'KODEX200USDT','NAVERUSDT','LGELECTRONICSUSDT','HANMIUSDT','SAMSUNGELUSDT',
   'CXMTUSDT','ZHONGJIUSDT','CSOPSAMSUNG2LUSDT','CSOPSKHYNIX2LUSDT'
 )
   and fr.funding_time >= timestamptz '2026-08-28 00:00:00+00'
 group by 1,2
 order by 1,2;

-- 3. O gap real (segundos) entre settlements consecutivos por símbolo, para
--    comparar contra o que `_cadence()` (moda global x moda recente) leria.
select symbol, funding_time,
       extract(epoch from (funding_time - lag(funding_time) over (partition by symbol order by funding_time))) as gap_s
  from (
    select m.symbol, fr.funding_time
      from funding_rates fr
      join markets m on m.id = fr.market_id
     where m.symbol in (
       'KODEX200USDT','NAVERUSDT','LGELECTRONICSUSDT','HANMIUSDT','SAMSUNGELUSDT',
       'CXMTUSDT','ZHONGJIUSDT','CSOPSAMSUNG2LUSDT','CSOPSKHYNIX2LUSDT'
     )
       and fr.funding_time >= timestamptz '2026-08-28 00:00:00+00'
  ) t
 order by symbol, funding_time;

commit;
