-- T3.53 q00 — catálogo da população: quantos desfechos existem, de quem, em que
-- coorte, com que janela de barras e com que cobertura de regime horário.
-- SOMENTE LEITURA (repeatable read / read only). Executável sozinho.
--
-- CORTE DECLARADO (as_of): agent_signals.emitted_at < 2026-09-09T02:30:00Z
--                          (= 2026-09-08 23:30 em Brasília, UTC-3).
-- O corte fixa a EMISSÃO, não a RESOLUÇÃO: releitura devolve n maiores porque o
-- Lab segue resolvendo acompanhamentos abertos ([[KB-0076]]).
--
-- POPULAÇÃO: desfecho terminal com r_multiple não nulo. Os terminais SEM
-- r_multiple (invalidação antes da entrada, sobretudo) aparecem na tabela 0 para
-- que a diferença entre "terminal" e "avaliável" seja visível, e não entram em
-- nenhuma média.
--
-- BARRA DE ORIGEM: meta->'entry_plan'->>'source_bar_close' — a última vela
-- fechada que a estratégia leu. É o relógio desta nota (hora, dia da semana,
-- junção com regime), nunca entry_ts nem emitted_at.
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at_utc, now() at time zone 'America/Sao_Paulo' as read_at_brt;

\echo ''
\echo '== 0. terminal x avaliavel (o que o corte deixa de fora) =='
select o.tracking_state::text as estado, o.result::text as motivo, count(*) as n,
       count(*) filter (where o.r_multiple is null) as sem_r
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
 where a.emitted_at < timestamptz '2026-09-09 02:30:00+00'
 group by 1,2 order by 1, 3 desc;

\echo ''
\echo '== 1. catalogo por versao x coorte =='
with pop as (
  select s.key as familia,
         s.key || ' ' || sv.version as versao,
         case when coalesce(a.supporting_features->>'cohort', o.meta->>'cohort', '') like 'replay:%'
              then 'replay' else 'prospective' end as coorte,
         m.symbol,
         (o.meta->'entry_plan'->>'source_bar_close')::timestamptz as bar,
         o.result::text as motivo,
         o.r_multiple as r_net,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk
    from signal_outcomes o
    join agent_signals a      on a.id  = o.signal_id
    join markets m            on m.id  = a.market_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id  = sv.strategy_id
   where a.emitted_at < timestamptz '2026-09-09 02:30:00+00'
     and o.tracking_state = 'terminal'
     and o.r_multiple is not null
)
select versao, coorte, count(*) as n,
       count(distinct symbol) as mercados,
       count(distinct (bar at time zone 'America/Sao_Paulo')::date) as dias_br,
       min(bar) as barra_min, max(bar) as barra_max,
       round(avg(r_net), 4) as exp_liquida_r,
       round(sum(r_net), 2) as soma_r,
       round(100.0 * count(*) filter (where motivo = 'target') / count(*), 1) as acerto_pct,
       round(sum(r_net) filter (where r_net > 0) / nullif(-sum(r_net) filter (where r_net < 0), 0), 3) as pf,
       round(avg(0.0020 / nullif(risk / nullif(p_entry, 0), 0)), 4) as custo_r_identidade,
       count(*) filter (where bar is null) as sem_barra
  from pop group by 1,2 order by 3 desc;

\echo ''
\echo '== 2. familias (pool de versoes) =='
with pop as (
  select s.key as familia,
         case when coalesce(a.supporting_features->>'cohort', o.meta->>'cohort', '') like 'replay:%'
              then 'replay' else 'prospective' end as coorte,
         o.r_multiple as r_net
    from signal_outcomes o
    join agent_signals a      on a.id  = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id  = sv.strategy_id
   where a.emitted_at < timestamptz '2026-09-09 02:30:00+00'
     and o.tracking_state = 'terminal' and o.r_multiple is not null
)
select familia, coorte, count(*) as n, round(avg(r_net),4) as exp_liquida_r, round(sum(r_net),2) as soma_r
  from pop group by 1,2 order by 1,2;

\echo ''
\echo '== 3. cobertura do regime horario do BTC (end_time <= barra de origem) =='
with reg as (
  select start_time, end_time, regime::text as regime,
         supporting_features->>'trend' as trend,
         supporting_features->>'vol_regime' as vol
    from market_regimes
   where scope = 'btc' and classifier_version like 'regime_hourly_v1%'
), pop as (
  select s.key || ' ' || sv.version as versao,
         (o.meta->'entry_plan'->>'source_bar_close')::timestamptz as bar
    from signal_outcomes o
    join agent_signals a      on a.id  = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id  = sv.strategy_id
   where a.emitted_at < timestamptz '2026-09-09 02:30:00+00'
     and o.tracking_state = 'terminal' and o.r_multiple is not null
), j as (
  select p.versao, coalesce(r.regime, 'SEM_LINHA') as regime,
         coalesce(r.trend, 'sem_linha') as trend, coalesce(r.vol, 'sem_linha') as vol
    from pop p
    left join lateral (
      select * from reg where reg.end_time <= p.bar order by reg.end_time desc limit 1
    ) r on true
)
select regime, trend, vol, count(*) as n,
       round(100.0 * count(*) / sum(count(*)) over (), 1) as pct
  from j group by 1,2,3 order by 4 desc;

\echo ''
\echo '== 3b. rotulos distintos da serie horaria =='
select regime::text, count(*) as horas from market_regimes
 where scope='btc' and classifier_version like 'regime_hourly_v1%' group by 1 order by 2 desc;
commit;
