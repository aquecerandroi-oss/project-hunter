-- T3.65b q00 -- A CADENCIA REAL DE PROM/SAHARA/TAO NOS 90 DIAS.
-- O `fapi/v1/fundingInfo` de hoje diz que estes tres estao em 4 h e os outros 13
-- do universo em 8 h (plantao run 5, faixa 1, item 3). Isso e o ESTADO DE AGORA;
-- nao reconstroi os 90 dias. Esta consulta le a serie que temos:
--   1. contagem, primeiro e ultimo assentamento por mercado;
--   2. histograma dos gaps entre assentamentos distintos (1 h / 4 h / 8 h / outro);
--   3. o dia em que o gap muda de 8 h para 4 h (a transicao), com os instantes
--      vizinhos -- e o mesmo teste para qualquer transicao (4h->1h, 1h->4h...);
--   4. os assentamentos de PROMUSDT entre 12/08 e 16/08, um por linha, para que o
--      teste de unidade seja construido sobre INSTANTES REAIS, nao sinteticos.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

-- 1. cobertura por mercado
with mkt as (
  select m.id, m.symbol
    from markets m
    join exchanges e on e.id = m.exchange_id
   where e.code = 'binance' and m.market_type = 'perpetual'
     and m.symbol in ('PROMUSDT','SAHARAUSDT','TAOUSDT','BTCUSDT')
)
select k.symbol,
       count(f.*)          as assentamentos,
       min(f.funding_time) as primeiro,
       max(f.funding_time) as ultimo
  from mkt k
  left join funding_rates f
         on f.market_id = k.id
        and f.funding_time >= timestamptz '2026-06-12 00:00+00'
        and f.funding_time <  timestamptz '2026-09-11 00:00+00'
 group by 1
 order by 1;

-- 2. histograma dos gaps (segundos) entre assentamentos consecutivos
with mkt as (
  select m.id, m.symbol
    from markets m
    join exchanges e on e.id = m.exchange_id
   where e.code = 'binance' and m.market_type = 'perpetual'
     and m.symbol in ('PROMUSDT','SAHARAUSDT','TAOUSDT','BTCUSDT')
), seq as (
  select k.symbol, f.funding_time,
         lag(f.funding_time) over (partition by k.symbol order by f.funding_time) as anterior
    from funding_rates f
    join mkt k on k.id = f.market_id
   where f.funding_time >= timestamptz '2026-06-12 00:00+00'
     and f.funding_time <  timestamptz '2026-09-11 00:00+00'
)
select symbol,
       round(extract(epoch from (funding_time - anterior)))::bigint as gap_s,
       count(*) as n,
       min(funding_time) as primeiro_com_esse_gap,
       max(funding_time) as ultimo_com_esse_gap
  from seq
 where anterior is not null
 group by 1, 2
 order by 1, 2;

-- 3. as transicoes: toda vez que o gap muda de valor
with mkt as (
  select m.id, m.symbol
    from markets m
    join exchanges e on e.id = m.exchange_id
   where e.code = 'binance' and m.market_type = 'perpetual'
     and m.symbol in ('PROMUSDT','SAHARAUSDT','TAOUSDT','BTCUSDT')
), seq as (
  select k.symbol, f.funding_time,
         lag(f.funding_time) over (partition by k.symbol order by f.funding_time) as anterior
    from funding_rates f
    join mkt k on k.id = f.market_id
   where f.funding_time >= timestamptz '2026-06-12 00:00+00'
     and f.funding_time <  timestamptz '2026-09-11 00:00+00'
), gaps as (
  select symbol, funding_time, anterior,
         round(extract(epoch from (funding_time - anterior)))::bigint as gap_s
    from seq where anterior is not null
), mud as (
  select symbol, funding_time, anterior, gap_s,
         lag(gap_s) over (partition by symbol order by funding_time) as gap_anterior
    from gaps
)
select symbol, gap_anterior as gap_s_antes, gap_s as gap_s_depois,
       anterior as ultimo_da_grade_antiga, funding_time as primeiro_da_grade_nova
  from mud
 where gap_anterior is not null and gap_anterior <> gap_s
 order by symbol, funding_time;

-- 4. PROMUSDT ao redor de 14/08 -- os instantes reais que o teste vai usar
with mkt as (
  select m.id, m.symbol
    from markets m
    join exchanges e on e.id = m.exchange_id
   where e.code = 'binance' and m.market_type = 'perpetual'
     and m.symbol = 'PROMUSDT'
)
select f.funding_time, f.rate, f.mark_price,
       round(extract(epoch from (f.funding_time
         - lag(f.funding_time) over (order by f.funding_time))))::bigint as gap_s
  from funding_rates f
  join mkt k on k.id = f.market_id
 where f.funding_time >= timestamptz '2026-08-12 00:00+00'
   and f.funding_time <  timestamptz '2026-08-16 00:00+00'
 order by f.funding_time;

commit;
