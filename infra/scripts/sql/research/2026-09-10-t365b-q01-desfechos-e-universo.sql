-- T3.65b q01 -- (a) HISTOGRAMA DE GAPS NOS 16 MERCADOS (lacuna de coleta x mudanca
-- real de cadencia) e (b) OS DESFECHOS de PROM/SAHARA/TAO por semana, com o motivo
-- de `r_net_reason`, antes e depois das transicoes medidas na q00.
-- A q00 mostrou que a premissa "PROM passou de 8 h para 4 h em 14/08" NAO e o que
-- a serie diz: PROM ja estava em 4 h em 12/06, ACELEROU para 1 h em 2026-08-11
-- 05:00Z e VOLTOU para 4 h em 2026-08-14 (10:00 -> 12:00 -> 16:00). A transicao
-- real de 14/08 e 1 h -> 4 h, exatamente o caso em que a Astra previu
-- `funding_missing` falso.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

-- 1. gaps por mercado nos 16 do universo: quantos valores distintos de gap
with mkt as (
  select m.id, m.symbol
    from markets m
    join exchanges e on e.id = m.exchange_id
   where e.code = 'binance' and m.market_type = 'perpetual'
     and m.symbol in ('BTCUSDT','ETHUSDT','ZECUSDT','SOLUSDT','XRPUSDT','BNBUSDT',
                      'DOGEUSDT','SUIUSDT','NEARUSDT','UNIUSDT','ARBUSDT','TAOUSDT',
                      'LINKUSDT','DASHUSDT','PROMUSDT','SAHARAUSDT')
), seq as (
  select k.symbol, f.funding_time,
         lag(f.funding_time) over (partition by k.symbol order by f.funding_time) as anterior
    from funding_rates f
    join mkt k on k.id = f.market_id
   where f.funding_time >= timestamptz '2026-06-12 00:00+00'
     and f.funding_time <  timestamptz '2026-09-11 00:00+00'
), g as (
  select symbol, funding_time,
         round(extract(epoch from (funding_time - anterior)))::bigint as gap_s
    from seq where anterior is not null
)
select symbol,
       count(*)                                        as gaps,
       count(*) filter (where gap_s = 3600)            as g_1h,
       count(*) filter (where gap_s = 14400)           as g_4h,
       count(*) filter (where gap_s = 28800)           as g_8h,
       count(*) filter (where gap_s not in (3600,14400,28800)) as g_outro,
       min(gap_s) as gap_min, max(gap_s) as gap_max
  from g
 group by 1
 order by 1;

-- 2. os gaps "outro" e "8h" nos mercados de 4h -- lacuna de coleta ou mudanca?
with mkt as (
  select m.id, m.symbol
    from markets m
    join exchanges e on e.id = m.exchange_id
   where e.code = 'binance' and m.market_type = 'perpetual'
     and m.symbol in ('BTCUSDT','ETHUSDT','ZECUSDT','SOLUSDT','XRPUSDT','BNBUSDT',
                      'DOGEUSDT','SUIUSDT','NEARUSDT','UNIUSDT','ARBUSDT','TAOUSDT',
                      'LINKUSDT','DASHUSDT','PROMUSDT','SAHARAUSDT')
), seq as (
  select k.symbol, f.funding_time,
         lag(f.funding_time) over (partition by k.symbol order by f.funding_time) as anterior
    from funding_rates f
    join mkt k on k.id = f.market_id
   where f.funding_time >= timestamptz '2026-06-12 00:00+00'
     and f.funding_time <  timestamptz '2026-09-11 00:00+00'
)
select symbol, anterior, funding_time,
       round(extract(epoch from (funding_time - anterior)))::bigint as gap_s
  from seq
 where anterior is not null
   and round(extract(epoch from (funding_time - anterior)))::bigint
       not in (case when symbol in ('PROMUSDT','SAHARAUSDT','TAOUSDT') then 14400 else 28800 end)
 order by symbol, funding_time;

-- 3. desfechos terminais dos tres mercados, por semana ISO, com motivo
select m.symbol,
       date_trunc('week', o.entry_ts)::date as semana,
       coalesce(split_part(o.meta->>'r_net_reason', ':', 1), 'ok') as motivo,
       count(*) as n
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  join markets m on m.id = a.market_id
 where o.tracking_state = 'terminal'
   and m.symbol in ('PROMUSDT','SAHARAUSDT','TAOUSDT')
 group by 1, 2, 3
 order by 1, 2, 3;

-- 4. o mesmo, so os que atravessam as transicoes de PROM (11/08 e 14/08)
select m.symbol, a.supporting_features->>'cohort' as cohort,
       o.entry_ts, o.exit_ts,
       o.meta->>'r_net_reason' as motivo,
       o.r_multiple
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  join markets m on m.id = a.market_id
 where o.tracking_state = 'terminal'
   and m.symbol = 'PROMUSDT'
   and o.entry_ts >= timestamptz '2026-08-10 00:00+00'
   and o.entry_ts <  timestamptz '2026-08-16 00:00+00'
 order by o.entry_ts;

-- 5. quantos desfechos terminais existem por mercado nos 16, para dar denominador
select m.symbol,
       count(*)                                          as terminais,
       count(o.r_multiple)                               as com_r_net,
       count(*) filter (where o.r_multiple is null)      as nulos,
       min(o.entry_ts) as primeiro, max(o.entry_ts) as ultimo
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  join markets m on m.id = a.market_id
 where o.tracking_state = 'terminal'
 group by 1
 order by 3 desc, 1;

commit;
