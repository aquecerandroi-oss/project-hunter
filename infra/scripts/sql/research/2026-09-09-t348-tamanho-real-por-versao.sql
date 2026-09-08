-- T3.48 (complemento 3) — o TAMANHO QUE O MOTOR APROVARIA, por versão viva.
--
-- A consulta anterior mostrou que, para a linha `paper` (momentum v3), o teto
-- vencedor é `market_participation` em 164 de 176 mercados. Esta generaliza para
-- todas as versões que decidiram nas últimas 24 h e devolve, por versão:
--   • o notional que venceria o mínimo dos tetos (por mercado, ponderado pelos sinais)
--   • o DINHEIRO POR 1 R = notional x distância do stop  (é isto que converte a
--     expectância em R$ — não o rótulo de 0,25 %)
--   • o risco real por operação em fração do patrimônio = notional x (stop + custo) / equity
-- em três tamanhos de `risk_per_trade_pct`: 0,25 % (hoje), 0,50 %, 1,00 %.
--
-- Mesmas aproximações declaradas do arquivo `...-qual-teto-vence.sql`:
-- referência de volume = mediana das barras de 1 min das últimas 24 h; custo de
-- ida e volta 0,0020; equity 19 333,0111164813 USDT; nenhuma posição aberta na
-- moeda (é o caso: `positions` está vazia).
-- Tetos ignorados aqui por não morderem nesta faixa: total_exposure (40 %),
-- beta_exposure (50 %/|β|), cash (100 %), book_depth (precisa do livro do
-- instante). Todos são MAIORES que os três calculados, então o mínimo não muda.
\pset border 2
\pset numericlocale off

begin transaction isolation level repeatable read read only;

\echo '== 0. corte da leitura =='
select now() as read_at, now() at time zone 'America/Sao_Paulo' as read_at_brasilia;

\echo ''
\echo '== H. por versao viva: teto vencedor, notional aprovado, dinheiro por 1 R e risco real =='
with dec as (
  select s.key || ' ' || sv.version as versao, a.market_id, count(*) as sinais,
         percentile_cont(0.50) within group (
           order by (o.meta->'excursions'->>'initial_risk')::numeric
                    / nullif((o.meta->'progress'->>'entry')::numeric / 1.0006, 0)) as stop_pct
    from agent_signals a
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
    left join signal_outcomes o on o.signal_id = a.id and o.tracking_state = 'terminal'
   where a.emitted_at > now() - interval '24 hours' and sv.status = 'active'
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
  select d.versao, d.sinais, d.stop_pct,
         19333.0111164813 * 0.10 as teto_moeda,
         0.01 * v.min_p50 as teto_part,
         19333.0111164813 * 0.0025 / (d.stop_pct + 0.0020) as t025,
         19333.0111164813 * 0.0050 / (d.stop_pct + 0.0020) as t050,
         19333.0111164813 * 0.0100 / (d.stop_pct + 0.0020) as t100
    from dec d join vol v on v.market_id = d.market_id
   where d.stop_pct is not null and v.min_p50 > 0
), n as (
  select versao, sinais, stop_pct,
         least(t025, teto_moeda, teto_part) as n025,
         least(t050, teto_moeda, teto_part) as n050,
         least(t100, teto_moeda, teto_part) as n100,
         case when t025 <= least(teto_moeda, teto_part) then 'risk_per_trade'
              when teto_part <= teto_moeda then 'market_participation'
              else 'asset_exposure' end as vence025,
         case when t100 <= least(teto_moeda, teto_part) then 'risk_per_trade'
              when teto_part <= teto_moeda then 'market_participation'
              else 'asset_exposure' end as vence100
    from calc
)
select versao, count(*) mercados, sum(sinais) sinais_24h,
       round(percentile_cont(0.50) within group (order by stop_pct)::numeric, 5) stop_pct_p50,
       round(percentile_cont(0.50) within group (order by n025)::numeric, 1) notional_025,
       round(percentile_cont(0.50) within group (order by n050)::numeric, 1) notional_050,
       round(percentile_cont(0.50) within group (order by n100)::numeric, 1) notional_100,
       round(percentile_cont(0.50) within group (order by n025 * stop_pct)::numeric, 3) usdt_por_R_025,
       round(percentile_cont(0.50) within group (order by n100 * stop_pct)::numeric, 3) usdt_por_R_100,
       round(percentile_cont(0.50) within group
             (order by n025 * (stop_pct + 0.0020) / 19333.0111164813)::numeric, 6) risco_real_025,
       round(percentile_cont(0.50) within group
             (order by n100 * (stop_pct + 0.0020) / 19333.0111164813)::numeric, 6) risco_real_100,
       count(*) filter (where vence025 = 'market_participation') part_025,
       count(*) filter (where vence025 = 'asset_exposure')       moeda_025,
       count(*) filter (where vence025 = 'risk_per_trade')       risco_025,
       count(*) filter (where vence100 = 'risk_per_trade')       risco_100
  from n group by 1 order by 3 desc;

\echo ''
\echo '== I. quantos sinais ficariam ABAIXO do min_notional do mercado (check 18 rejeita) =='
with dec as (
  select s.key || ' ' || sv.version as versao, a.market_id, m.min_notional, count(*) as sinais,
         percentile_cont(0.50) within group (
           order by (o.meta->'excursions'->>'initial_risk')::numeric
                    / nullif((o.meta->'progress'->>'entry')::numeric / 1.0006, 0)) as stop_pct
    from agent_signals a
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
    join markets m on m.id = a.market_id
    left join signal_outcomes o on o.signal_id = a.id and o.tracking_state = 'terminal'
   where a.emitted_at > now() - interval '24 hours' and sv.status = 'active'
   group by 1, 2, 3
), vol as (
  select c.market_id,
         percentile_cont(0.50) within group (order by c.quote_volume) as min_p50
    from candles c
   where c.timeframe = '1m' and c.is_final
     and c.open_time > now() - interval '24 hours'
     and c.market_id in (select market_id from dec)
   group by 1
), n as (
  select d.versao, d.sinais, coalesce(d.min_notional, 5) as min_notional,
         least(19333.0111164813 * 0.0025 / (d.stop_pct + 0.0020),
               19333.0111164813 * 0.10, 0.01 * v.min_p50) as n025
    from dec d join vol v on v.market_id = d.market_id
   where d.stop_pct is not null and v.min_p50 > 0
)
select versao, count(*) mercados, sum(sinais) sinais,
       count(*) filter (where n025 < min_notional) mercados_abaixo_do_minimo,
       sum(sinais) filter (where n025 < min_notional) sinais_rejeitados_pelo_check18,
       round(percentile_cont(0.50) within group (order by min_notional)::numeric, 2) min_notional_p50
  from n group by 1 order by 3 desc;

commit;
