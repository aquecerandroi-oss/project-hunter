-- T3.60 q00 — catálogo: a família mean_reversion como ela está, a carteira paper,
-- o perfil de risco em vigor e a concorrência que o Lab pediria.
--
-- SOMENTE LEITURA (repeatable read read only). Executável sozinho, sem tabela
-- temporária (proibida em transação read only), por isso o CTE `pop` se repete —
-- convenção de `infra/scripts/sql/research/2026-09-08-00-base.sql`.
--
-- DIA DE NEGOCIAÇÃO = America/Sao_Paulo (RISK_ENGINE.md §5), nunca UTC.
-- RELÓGIO DA DECISÃO = meta->'entry_plan'->>'source_bar_close' (a última vela
-- fechada que a estratégia leu); `entry_ts` é a barra seguinte, onde a ordem
-- entraria de fato — é ele que o simulador usa como instante da proposta.
\pset border 2
\pset numericlocale off

begin transaction isolation level repeatable read read only;

\echo '== 0. corte da leitura =='
select now() as read_at_utc, now() at time zone 'America/Sao_Paulo' as read_at_brasilia;

\echo ''
\echo '== 1. versões da família mean_reversion =='
select s.key || ' ' || sv.version as versao, sv.purpose, sv.status, sv.activated_at,
       sv.default_parameters->>'stop_atr'    as stop_atr,
       sv.default_parameters->>'target_atr'  as target_atr,
       sv.default_parameters->>'atr_pct_min' as atr_pct_min,
       sv.default_parameters->>'atr_pct_max' as atr_pct_max
  from strategy_versions sv
  join strategies s on s.id = sv.strategy_id
 where s.key = 'mean_reversion'
 order by sv.activated_at;

\echo ''
\echo '== 2. carteira paper e perfil de risco persistido =='
select p.name, p.type, p.status, p.kill_switch_state, p.base_currency, p.initial_capital,
       p.risk_profile_id,
       (select count(*) from trade_proposals) as propostas,
       (select count(*) from orders)          as ordens,
       (select count(*) from positions)       as posicoes,
       (select count(*) from risk_events)     as risk_events
  from portfolios p
 where p.deleted_at is null and p.type = 'paper';

\echo ''
\echo '== 3. desfechos avaliáveis por versão × coorte (toda a família) =='
with pop as (
  select s.key || ' ' || sv.version as versao,
         case when coalesce(a.supporting_features->>'cohort', o.meta->>'cohort', '') like 'replay:%'
              then 'replay' else 'prospective' end as coorte,
         o.entry_ts, o.exit_ts, o.r_multiple as r_net, o.result::text as motivo
    from signal_outcomes o
    join agent_signals a      on a.id  = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id  = sv.strategy_id
   where s.key = 'mean_reversion'
     and o.tracking_state = 'terminal' and o.r_multiple is not null
     and o.entry_ts is not null and o.exit_ts is not null
)
select versao, coorte, count(*) n,
       count(distinct (entry_ts at time zone 'America/Sao_Paulo')::date) dias_br,
       min(entry_ts) de, max(exit_ts) ate,
       round(sum(r_net), 2) soma_r, round(avg(r_net), 4) exp_r,
       round(100.0 * count(*) filter (where motivo = 'target') / count(*), 1) acerto_pct,
       round(avg(extract(epoch from (exit_ts - entry_ts)) / 3600.0)::numeric, 2) horas_media
  from pop group by 1, 2 order by 2, 1;

\echo ''
\echo '== 4. o pooling: operações x apostas distintas (mercado × barra de origem), por dia BR =='
with pop as (
  select s.key || ' ' || sv.version as versao,
         case when coalesce(a.supporting_features->>'cohort', o.meta->>'cohort', '') like 'replay:%'
              then 'replay' else 'prospective' end as coorte,
         a.market_id,
         (o.meta->'entry_plan'->>'source_bar_close')::timestamptz as bar,
         o.entry_ts, o.r_multiple as r_net
    from signal_outcomes o
    join agent_signals a      on a.id  = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id  = sv.strategy_id
   where s.key = 'mean_reversion'
     and o.tracking_state = 'terminal' and o.r_multiple is not null
     and o.entry_ts is not null
)
select coorte, (entry_ts at time zone 'America/Sao_Paulo')::date as dia_br,
       count(*) operacoes,
       count(distinct (market_id::text || '|' || bar::text)) apostas_barra,
       count(distinct (market_id::text || '|' ||
             date_trunc('hour', bar)::text))                   apostas_hora,
       count(distinct market_id) mercados,
       count(distinct versao) versoes,
       round(count(*)::numeric / nullif(count(distinct (market_id::text || '|' || bar::text)), 0), 2) pooling_barra,
       round(sum(r_net), 2) soma_r
  from pop group by 1, 2 order by 1, 2;

\echo ''
\echo '== 5. posições simultâneas que a família pediria (sem nenhum limite) =='
with pop as (
  select case when coalesce(a.supporting_features->>'cohort', o.meta->>'cohort', '') like 'replay:%'
              then 'replay' else 'prospective' end as coorte,
         o.entry_ts, o.exit_ts
    from signal_outcomes o
    join agent_signals a      on a.id  = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id  = sv.strategy_id
   where s.key = 'mean_reversion'
     and o.tracking_state = 'terminal' and o.r_multiple is not null
     and o.entry_ts is not null and o.exit_ts is not null
), ev as (
  select coorte, entry_ts as t, 1 as d from pop
  union all
  select coorte, exit_ts as t, -1 as d from pop
), run as (
  select coorte, t, sum(d) over (partition by coorte order by t, d desc
                                 rows between unbounded preceding and current row) as abertas
    from ev
)
select coorte, max(abertas) as pico_simultaneo,
       round(avg(abertas), 2) as media_simultanea,
       count(*) filter (where abertas > 5) as eventos_acima_de_5,
       round(100.0 * count(*) filter (where abertas > 5) / count(*), 1) as pct_eventos_acima_de_5
  from run group by 1 order by 1;

commit;
