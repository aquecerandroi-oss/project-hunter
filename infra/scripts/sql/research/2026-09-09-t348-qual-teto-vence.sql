-- T3.48 (complemento 2) — QUAL TETO DE FATO DECIDE O TAMANHO HOJE.
--
-- A pergunta do documento é "o que muda se `risk_per_trade_pct` subir de 0,25 %".
-- A resposta só é honesta se soubermos se esse teto é o que vence hoje. O sizing
-- (`packages/risk-core/hunter_risk/sizing.py:139-207`, RISK_ENGINE §4) toma o
-- MÍNIMO entre nove tetos, todos em notional:
--   risk_per_trade     = equity x s / (stop_dist + custo)
--   asset_exposure     = equity x 0,10        (nenhuma posição na moeda ainda)
--   total_exposure     = equity x 0,40
--   market_participation = 0,01 x volume_de_referência_do_minuto
--   beta_exposure      = equity x 0,50 / |beta|
--   cash               = caixa / (1 + taxa)
-- Esta consulta calcula os três primeiros e o de participação com o volume REAL
-- de cada mercado que decidiu nas últimas 24 h, e diz qual venceria — em três
-- tamanhos: 0,25 % (hoje), 0,50 % e 1,00 %.
--
-- REFERÊNCIA DE VOLUME: o contrato usa min(último minuto completo, mediana de 30
-- barras). Aqui uso a MEDIANA das barras de 1 min das últimas 24 h como valor
-- típico e o p10 como minuto fraco — é uma aproximação declarada, não o número
-- que o motor usaria naquele instante.
-- CUSTO: 20 bps de ida e volta (`assumed_costs` de todas as linhas do banco:
-- fee 4 + spread 2 + slippage 5 por perna => 0,0020 no total, base.sql).
-- EQUITY: 19 333,0111164813 USDT (consulta 2 da primeira SQL) = R$100.000.
\pset border 2
\pset numericlocale off

begin transaction isolation level repeatable read read only;

\echo '== 0. corte da leitura =='
select now() as read_at, now() at time zone 'America/Sao_Paulo' as read_at_brasilia;

\echo ''
\echo '== E. por mercado que decidiu nas ultimas 24 h (momentum v3, a linha paper): qual teto vence =='
with dec as (
  select a.market_id, m.symbol,
         count(*) as sinais,
         percentile_cont(0.50) within group (
           order by (o.meta->'excursions'->>'initial_risk')::numeric
                    / nullif((o.meta->'progress'->>'entry')::numeric / 1.0006, 0)) as stop_pct_p50
    from agent_signals a
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
    join markets m on m.id = a.market_id
    left join signal_outcomes o on o.signal_id = a.id and o.tracking_state = 'terminal'
   where s.key = 'momentum' and sv.version = 'v3'
     and a.emitted_at > now() - interval '24 hours'
   group by 1, 2
), vol as (
  select c.market_id,
         percentile_cont(0.50) within group (order by c.quote_volume) as min_p50,
         percentile_cont(0.10) within group (order by c.quote_volume) as min_p10,
         count(*) as barras
    from candles c
   where c.timeframe = '1m' and c.is_final
     and c.open_time > now() - interval '24 hours'
     and c.market_id in (select market_id from dec)
   group by 1
), calc as (
  select d.symbol, d.sinais, round(d.stop_pct_p50::numeric, 5) as stop_pct,
         round(v.min_p50::numeric, 0) as vol_minuto_p50,
         round((19333.0111164813 * 0.0025 / nullif(d.stop_pct_p50 + 0.0020, 0))::numeric, 0) as teto_risco_025,
         round((19333.0111164813 * 0.0050 / nullif(d.stop_pct_p50 + 0.0020, 0))::numeric, 0) as teto_risco_050,
         round((19333.0111164813 * 0.0100 / nullif(d.stop_pct_p50 + 0.0020, 0))::numeric, 0) as teto_risco_100,
         round((19333.0111164813 * 0.10)::numeric, 0) as teto_moeda,
         round((0.01 * v.min_p50)::numeric, 0) as teto_participacao
    from dec d join vol v on v.market_id = d.market_id
   where d.stop_pct_p50 is not null
)
select symbol, sinais, stop_pct, vol_minuto_p50,
       teto_risco_025, teto_moeda, teto_participacao,
       case when teto_risco_025 <= least(teto_moeda, teto_participacao) then 'risk_per_trade'
            when teto_participacao <= teto_moeda then 'market_participation'
            else 'asset_exposure' end as vence_a_025,
       case when teto_risco_050 <= least(teto_moeda, teto_participacao) then 'risk_per_trade'
            when teto_participacao <= teto_moeda then 'market_participation'
            else 'asset_exposure' end as vence_a_050,
       case when teto_risco_100 <= least(teto_moeda, teto_participacao) then 'risk_per_trade'
            when teto_participacao <= teto_moeda then 'market_participation'
            else 'asset_exposure' end as vence_a_100
  from calc order by sinais desc limit 25;

\echo ''
\echo '== F. o resumo: em quantos mercados/sinais cada teto vence, por tamanho =='
with dec as (
  select a.market_id, m.symbol, count(*) as sinais,
         percentile_cont(0.50) within group (
           order by (o.meta->'excursions'->>'initial_risk')::numeric
                    / nullif((o.meta->'progress'->>'entry')::numeric / 1.0006, 0)) as stop_pct_p50
    from agent_signals a
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
    join markets m on m.id = a.market_id
    left join signal_outcomes o on o.signal_id = a.id and o.tracking_state = 'terminal'
   where s.key = 'momentum' and sv.version = 'v3'
     and a.emitted_at > now() - interval '24 hours'
   group by 1, 2
), vol as (
  select c.market_id,
         percentile_cont(0.50) within group (order by c.quote_volume) as min_p50
    from candles c
   where c.timeframe = '1m' and c.is_final
     and c.open_time > now() - interval '24 hours'
     and c.market_id in (select market_id from dec)
   group by 1
), calc as (
  select d.symbol, d.sinais, d.stop_pct_p50 as stop_pct,
         19333.0111164813 * 0.10 as teto_moeda,
         0.01 * v.min_p50 as teto_part,
         19333.0111164813 * 0.0025 / (d.stop_pct_p50 + 0.0020) as t025,
         19333.0111164813 * 0.0050 / (d.stop_pct_p50 + 0.0020) as t050,
         19333.0111164813 * 0.0100 / (d.stop_pct_p50 + 0.0020) as t100
    from dec d join vol v on v.market_id = d.market_id
   where d.stop_pct_p50 is not null
), venc as (
  select symbol, sinais,
         case when t025 <= least(teto_moeda, teto_part) then 'risk_per_trade'
              when teto_part <= teto_moeda then 'market_participation'
              else 'asset_exposure' end as v025,
         case when t050 <= least(teto_moeda, teto_part) then 'risk_per_trade'
              when teto_part <= teto_moeda then 'market_participation'
              else 'asset_exposure' end as v050,
         case when t100 <= least(teto_moeda, teto_part) then 'risk_per_trade'
              when teto_part <= teto_moeda then 'market_participation'
              else 'asset_exposure' end as v100,
         least(t025, teto_moeda, teto_part) as n025,
         least(t050, teto_moeda, teto_part) as n050,
         least(t100, teto_moeda, teto_part) as n100,
         stop_pct
    from calc
)
select 'mercados' as unidade,
       count(*) filter (where v025 = 'risk_per_trade')       as risco_025,
       count(*) filter (where v025 = 'asset_exposure')       as moeda_025,
       count(*) filter (where v025 = 'market_participation') as particip_025,
       count(*) filter (where v050 = 'risk_per_trade')       as risco_050,
       count(*) filter (where v050 = 'asset_exposure')       as moeda_050,
       count(*) filter (where v050 = 'market_participation') as particip_050,
       count(*) filter (where v100 = 'risk_per_trade')       as risco_100,
       count(*) filter (where v100 = 'asset_exposure')       as moeda_100,
       count(*) filter (where v100 = 'market_participation') as particip_100
  from venc
union all
select 'sinais 24h',
       coalesce(sum(sinais) filter (where v025 = 'risk_per_trade'), 0),
       coalesce(sum(sinais) filter (where v025 = 'asset_exposure'), 0),
       coalesce(sum(sinais) filter (where v025 = 'market_participation'), 0),
       coalesce(sum(sinais) filter (where v050 = 'risk_per_trade'), 0),
       coalesce(sum(sinais) filter (where v050 = 'asset_exposure'), 0),
       coalesce(sum(sinais) filter (where v050 = 'market_participation'), 0),
       coalesce(sum(sinais) filter (where v100 = 'risk_per_trade'), 0),
       coalesce(sum(sinais) filter (where v100 = 'asset_exposure'), 0),
       coalesce(sum(sinais) filter (where v100 = 'market_participation'), 0)
  from venc;

\echo ''
\echo '== G. o tamanho medio aprovado (notional) e o RISCO REAL em % do patrimonio, por tamanho =='
with dec as (
  select a.market_id, count(*) as sinais,
         percentile_cont(0.50) within group (
           order by (o.meta->'excursions'->>'initial_risk')::numeric
                    / nullif((o.meta->'progress'->>'entry')::numeric / 1.0006, 0)) as stop_pct_p50
    from agent_signals a
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
    left join signal_outcomes o on o.signal_id = a.id and o.tracking_state = 'terminal'
   where s.key = 'momentum' and sv.version = 'v3'
     and a.emitted_at > now() - interval '24 hours'
   group by 1
), vol as (
  select c.market_id,
         percentile_cont(0.50) within group (order by c.quote_volume) as min_p50
    from candles c
   where c.timeframe = '1m' and c.is_final
     and c.open_time > now() - interval '24 hours'
     and c.market_id in (select market_id from dec)
   group by 1
), calc as (
  select d.stop_pct_p50 as stop_pct,
         least(19333.0111164813 * 0.0025 / (d.stop_pct_p50 + 0.0020),
               19333.0111164813 * 0.10, 0.01 * v.min_p50) as n025,
         least(19333.0111164813 * 0.0050 / (d.stop_pct_p50 + 0.0020),
               19333.0111164813 * 0.10, 0.01 * v.min_p50) as n050,
         least(19333.0111164813 * 0.0100 / (d.stop_pct_p50 + 0.0020),
               19333.0111164813 * 0.10, 0.01 * v.min_p50) as n100
    from dec d join vol v on v.market_id = d.market_id
   where d.stop_pct_p50 is not null
)
select count(*) as mercados,
       round(percentile_cont(0.50) within group (order by n025)::numeric, 0) as notional_p50_025,
       round(percentile_cont(0.50) within group (order by n050)::numeric, 0) as notional_p50_050,
       round(percentile_cont(0.50) within group (order by n100)::numeric, 0) as notional_p50_100,
       round(percentile_cont(0.50) within group
             (order by n025 * (stop_pct + 0.0020) / 19333.0111164813)::numeric, 5) as risco_real_025,
       round(percentile_cont(0.50) within group
             (order by n050 * (stop_pct + 0.0020) / 19333.0111164813)::numeric, 5) as risco_real_050,
       round(percentile_cont(0.50) within group
             (order by n100 * (stop_pct + 0.0020) / 19333.0111164813)::numeric, 5) as risco_real_100
  from calc;

commit;
