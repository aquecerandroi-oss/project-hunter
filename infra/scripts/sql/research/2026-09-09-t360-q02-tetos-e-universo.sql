-- T3.60 q02 — os dois tetos que decidem o tamanho, medidos no universo vivo:
-- o piso de liquidez de 24 h (check 9) e a referência de participação de 1 minuto
-- (§4). SOMENTE LEITURA. Recibo independente do simulador em Python: se as duas
-- fontes discordarem, é aqui que se vê.
--
-- Referência de participação do motor = min(último minuto completo, mediana das
-- 30 barras completas). Esta consulta usa a mediana das barras de 1 min das
-- últimas 24 h como PROXY da referência típica do mercado — é a mesma
-- aproximação declarada da T3.48, e serve para ordem de grandeza, não para o
-- instante exato de uma decisão (esse está no CSV de `q01`, barra a barra).
\pset border 2
\pset numericlocale off

begin transaction isolation level repeatable read read only;

\echo '== 0. corte da leitura =='
select now() as read_at_utc, now() at time zone 'America/Sao_Paulo' as read_at_brasilia;

\echo ''
\echo '== 1. universo monitorado: quantos mercados passam o piso de 50 M USD/24 h =='
with vol as (
  select c.market_id,
         sum(c.quote_volume) as vol_24h,
         percentile_cont(0.50) within group (order by c.quote_volume) as minuto_p50
    from candles c
   where c.timeframe = '1m' and c.is_final
     and c.open_time > now() - interval '24 hours'
   group by 1
)
select count(*) as mercados_com_velas,
       count(*) filter (where vol_24h >= 50000000) as passam_o_piso,
       round(100.0 * count(*) filter (where vol_24h >= 50000000) / count(*), 1) as pct_passam,
       round(percentile_cont(0.50) within group (order by vol_24h)::numeric / 1e6, 1) as vol24h_p50_M,
       round(percentile_cont(0.90) within group (order by vol_24h)::numeric / 1e6, 1) as vol24h_p90_M,
       round(percentile_cont(0.50) within group (order by 0.01 * minuto_p50)::numeric, 2) as teto_part_p50_usdt,
       round(percentile_cont(0.90) within group (order by 0.01 * minuto_p50)::numeric, 2) as teto_part_p90_usdt,
       round(max(0.01 * minuto_p50)::numeric, 2) as teto_part_max_usdt
  from vol;

\echo ''
\echo '== 2. os mercados em que a familia mean_reversion entrou hoje: teto de participacao =='
with mrk as (
  select distinct a.market_id, m.symbol
    from signal_outcomes o
    join agent_signals a      on a.id  = o.signal_id
    join markets m            on m.id  = a.market_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id  = sv.strategy_id
   where s.key = 'mean_reversion'
     and o.tracking_state = 'terminal' and o.r_multiple is not null
     and (o.entry_ts at time zone 'America/Sao_Paulo')::date = date '2026-09-09'
), vol as (
  select c.market_id,
         sum(c.quote_volume) as vol_24h,
         percentile_cont(0.50) within group (order by c.quote_volume) as minuto_p50
    from candles c
   where c.timeframe = '1m' and c.is_final
     and c.open_time > now() - interval '24 hours'
     and c.market_id in (select market_id from mrk)
   group by 1
)
select count(*) as mercados,
       count(*) filter (where vol_24h >= 50000000) as passam_o_piso_50M,
       round(percentile_cont(0.50) within group (order by vol_24h)::numeric / 1e6, 1) as vol24h_p50_M,
       round(percentile_cont(0.50) within group (order by 0.01 * minuto_p50)::numeric, 2) as teto_part_p50_usdt,
       round(percentile_cont(0.50) within group (order by 0.01 * minuto_p50)::numeric * 5.1725, 2) as teto_part_p50_brl,
       round(max(0.01 * minuto_p50)::numeric, 2) as teto_part_max_usdt
  from vol;

\echo ''
\echo '== 3. os dez mercados mais fundos do universo (onde um tamanho grande caberia) =='
with vol as (
  select c.market_id,
         sum(c.quote_volume) as vol_24h,
         percentile_cont(0.50) within group (order by c.quote_volume) as minuto_p50
    from candles c
   where c.timeframe = '1m' and c.is_final and c.open_time > now() - interval '24 hours'
   group by 1
)
select m.symbol,
       round(v.vol_24h::numeric / 1e6, 0) as vol24h_M,
       round((0.01 * v.minuto_p50)::numeric, 2) as teto_participacao_usdt,
       round((0.01 * v.minuto_p50 * 5.1725)::numeric, 2) as teto_participacao_brl,
       round((0.10 * 19333.0111164813)::numeric, 2) as teto_por_moeda_usdt_100k
  from vol v join markets m on m.id = v.market_id
 order by v.minuto_p50 desc limit 10;

\echo ''
\echo '== 4. a conta do R$ 9.000/dia: qual volume de minuto um R de R$ 3.725 exigiria =='
\echo '==    (1 R = notional x distancia do stop; stop mediano medido da familia)  =='
with stop as (
  select percentile_cont(0.50) within group (
           order by (o.meta->'excursions'->>'initial_risk')::numeric
                    / nullif((o.meta->'progress'->>'entry')::numeric / 1.0006, 0)) as stop_p50
    from signal_outcomes o
    join agent_signals a      on a.id  = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id  = sv.strategy_id
   where s.key = 'mean_reversion' and o.tracking_state = 'terminal' and o.r_multiple is not null
), alvo as (
  select 9000.0 / 5.1725 as meta_usdt_dia, 2.42 as r_unicos_dia, stop_p50 from stop
)
select round(stop_p50::numeric, 5) as stop_mediano,
       round((meta_usdt_dia / r_unicos_dia)::numeric, 2) as usdt_por_R_necessario,
       round((meta_usdt_dia / r_unicos_dia * 5.1725)::numeric, 2) as brl_por_R_necessario,
       round((meta_usdt_dia / r_unicos_dia / stop_p50)::numeric, 0) as notional_necessario_usdt,
       round((meta_usdt_dia / r_unicos_dia / stop_p50 * 10)::numeric, 0) as patrimonio_exigido_pelo_teto_moeda,
       round((meta_usdt_dia / r_unicos_dia / stop_p50 * 100)::numeric, 0) as minuto_de_volume_exigido_usdt,
       (select count(*) from (
          select c.market_id, percentile_cont(0.50) within group (order by c.quote_volume) as mp50
            from candles c
           where c.timeframe = '1m' and c.is_final and c.open_time > now() - interval '24 hours'
           group by 1) x
         where x.mp50 >= (select meta_usdt_dia / r_unicos_dia / stop_p50 * 100 from alvo)
       ) as mercados_que_comportariam
  from alvo;

\echo ''
\echo '== 5. quantos mercados do universo suportam cada tamanho de 1 R =='
\echo '==    (1 R = notional x stop; stop mediano 1,284 % das operacoes que o motor executou) =='
\echo '==    e o teto de participacao exige um minuto de 100x o notional (1 %)                =='
with vol as (
  select c.market_id,
         percentile_cont(0.50) within group (order by c.quote_volume) as minuto_p50,
         sum(c.quote_volume) as vol_24h
    from candles c
   where c.timeframe = '1m' and c.is_final and c.open_time > now() - interval '24 hours'
   group by 1
), alvos(brl_por_r) as (
  values (34.48), (50.0), (100.0), (250.0), (500.0), (1000.0), (3719.0)
)
select a.brl_por_r,
       round((a.brl_por_r / 5.1725)::numeric, 2)                        as usdt_por_r,
       round((a.brl_por_r / 5.1725 / 0.01284)::numeric, 0)              as notional_usdt,
       round((a.brl_por_r / 5.1725 / 0.01284 * 100)::numeric, 0)        as minuto_exigido_usdt,
       (select count(*) from vol
         where vol.minuto_p50 >= a.brl_por_r / 5.1725 / 0.01284 * 100)  as mercados_no_universo,
       (select count(*) from vol
         where vol.minuto_p50 >= a.brl_por_r / 5.1725 / 0.01284 * 100
           and vol.vol_24h >= 50000000)                                 as e_tambem_passam_50M
  from alvos a
 order by a.brl_por_r;

commit;
