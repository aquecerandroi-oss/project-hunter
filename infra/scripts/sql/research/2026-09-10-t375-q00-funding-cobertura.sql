-- T3.75 q00 -- COBERTURA DE `funding_rates` NOS 16 MERCADOS DA COORTE DE 90 DIAS.
-- A T3.62b mediu (notes-T3.62b SS3) que `funding_rates` so existe a partir de
-- 2026-08-08 16:00Z: o backfill de 90 dias da T3.62 trouxe VELA, nao FUNDING.
-- Esta consulta e a linha de base do antes/depois do backfill `--kind funding`
-- desta tarefa. Ela responde tres coisas, e nada mais:
--   1. primeiro/ultimo assentamento e contagem por mercado na janela de 90 d;
--   2. a mesma contagem por mes, para ver o degrau de 08/08 aparecer e sumir;
--   3. quantos assentamentos existem ANTES de 2026-08-08 16:00Z (o numero que
--      tem de sair de 0 para ~170/mercado depois do backfill).
-- Cadencia observada: 8 h (3/dia). 2026-06-12 -> 2026-08-08 = 57 dias -> ~171.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

with mkt as (
  select m.id, m.symbol
    from markets m
    join exchanges e on e.id = m.exchange_id
   where e.code = 'binance' and m.market_type = 'perpetual'
     and m.symbol in ('BTCUSDT','ETHUSDT','ZECUSDT','SOLUSDT','XRPUSDT','BNBUSDT',
                      'DOGEUSDT','SUIUSDT','NEARUSDT','UNIUSDT','ARBUSDT','TAOUSDT',
                      'LINKUSDT','DASHUSDT','PROMUSDT','SAHARAUSDT')
)
-- 1. por mercado, dentro da janela de 90 dias da coorte
select k.symbol,
       count(f.*)                             as assentamentos,
       min(f.funding_time)                    as primeiro,
       max(f.funding_time)                    as ultimo,
       count(*) filter (
         where f.funding_time < timestamptz '2026-08-08 16:00+00'
       )                                      as antes_de_0808
  from mkt k
  left join funding_rates f
         on f.market_id = k.id
        and f.funding_time >= timestamptz '2026-06-12 00:00+00'
        and f.funding_time <  timestamptz '2026-09-10 00:00+00'
 group by 1
 order by 1;

-- 2. o degrau, por mes (a CTE e por comando; repetida de proposito)
with mkt as (
  select m.id, m.symbol
    from markets m
    join exchanges e on e.id = m.exchange_id
   where e.code = 'binance' and m.market_type = 'perpetual'
     and m.symbol in ('BTCUSDT','ETHUSDT','ZECUSDT','SOLUSDT','XRPUSDT','BNBUSDT',
                      'DOGEUSDT','SUIUSDT','NEARUSDT','UNIUSDT','ARBUSDT','TAOUSDT',
                      'LINKUSDT','DASHUSDT','PROMUSDT','SAHARAUSDT')
)
select date_trunc('month', f.funding_time)::date as mes,
       count(distinct f.market_id)               as mercados,
       count(*)                                  as linhas,
       min(f.funding_time)                       as primeiro,
       max(f.funding_time)                       as ultimo
  from funding_rates f
  join mkt k on k.id = f.market_id
 where f.funding_time >= timestamptz '2026-06-12 00:00+00'
   and f.funding_time <  timestamptz '2026-09-10 00:00+00'
 group by 1
 order by 1;

-- 3. o total agregado, o unico numero que o antes/depois compara
with mkt as (
  select m.id, m.symbol
    from markets m
    join exchanges e on e.id = m.exchange_id
   where e.code = 'binance' and m.market_type = 'perpetual'
     and m.symbol in ('BTCUSDT','ETHUSDT','ZECUSDT','SOLUSDT','XRPUSDT','BNBUSDT',
                      'DOGEUSDT','SUIUSDT','NEARUSDT','UNIUSDT','ARBUSDT','TAOUSDT',
                      'LINKUSDT','DASHUSDT','PROMUSDT','SAHARAUSDT')
)
select count(*)                                        as linhas_totais,
       count(*) filter (
         where funding_time < timestamptz '2026-08-08 16:00+00'
       )                                               as linhas_antes_de_0808,
       count(distinct market_id)                       as mercados
  from funding_rates f
 where f.market_id in (select id from mkt)
   and f.funding_time >= timestamptz '2026-06-12 00:00+00'
   and f.funding_time <  timestamptz '2026-09-10 00:00+00';

commit;
