-- T3.43 — corte de qualquer coorte por regime (`market_regimes`, regime_hourly_v1).
--
-- Somente leitura. Executável sozinho: o bloco `pop` é repetido de propósito
-- (mesma convenção de `2026-09-08-00-base.sql`).
--
-- O QUE ESTA CONSULTA USA. A série horária que a T3.43 produz:
--   scope = 'btc', classifier_version LIKE 'regime_hourly_v1%',
--   uma linha por hora fechada, vigente em [start_time, start_time + 1h).
-- Cada linha foi decidida com velas `is_final` fechadas ANTES de `start_time`,
-- então juntar a entrada de um sinal com a hora que a contém não antecipa nada:
-- o rótulo da hora das 12:00 saiu de dados de até 12:00, e a entrada às 12:34
-- é julgada por contexto que já existia quando ela aconteceu.
--
-- `regime_v0` (o classificador vivo, scope='global') NÃO entra aqui: ele grava
-- por transição e tinha 1 linha em 2026-09-08. Os dois convivem na mesma tabela
-- e são separados por `scope` + `classifier_version`; nunca misture os dois numa
-- média.
--
-- LEITURA HONESTA. Onde a série ainda está em aquecimento (menos de 224 horas
-- fechadas de BTC para a tendência, menos de 193 para o percentil de
-- volatilidade), o rótulo é `unknown` — que é uma classificação, não um buraco.
-- As linhas `unknown` aparecem nas tabelas com esse nome em vez de sumirem, e
-- `sem_regime` é o sinal cuja hora não tem linha nenhuma.
\pset border 2
\pset numericlocale off

\echo '== 1. cobertura da serie horaria =='
select classifier_version,
       count(*) horas,
       min(start_time) de,
       max(start_time) ate,
       count(*) filter (where regime = 'UNKNOWN') aquecendo
  from market_regimes
 where scope = 'btc' and classifier_version like 'regime_hourly_v1%'
 group by 1 order by 1;

\echo ''
\echo '== 1b. distribuicao das horas por trend x vol_regime =='
select supporting_features ->> 'trend' as trend,
       supporting_features ->> 'vol_regime' as vol,
       count(*) horas,
       round(avg((supporting_features ->> 'score_0_100')::numeric), 1) score_medio,
       round(avg((supporting_features ->> 'breadth_pct')::numeric), 1) breadth_medio,
       round(avg((supporting_features ->> 'drawdown_pct')::numeric), 2) dd_medio
  from market_regimes
 where scope = 'btc' and classifier_version like 'regime_hourly_v1%'
 group by 1, 2 order by 1, 2;

\echo ''
\echo '== 2. desfechos por coorte x trend x vol_regime =='
with pop as (
  select o.signal_id,
         s.key || ' ' || sv.version as version,
         case when o.meta ->> 'cohort' like 'replay:%'
              then 'replay:' || left(split_part(o.meta ->> 'cohort', ':', 2), 8)
              else 'prospective' end as coorte,
         o.result, o.r_multiple as r_net, o.entry_ts
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
   where o.tracking_state = 'terminal' and o.r_multiple is not null
), reg as (
  select id, start_time, end_time,
         supporting_features ->> 'trend' as trend,
         supporting_features ->> 'vol_regime' as vol,
         (supporting_features ->> 'score_0_100')::numeric as score
    from market_regimes
   where scope = 'btc' and classifier_version like 'regime_hourly_v1%'
), j as (
  select p.*, coalesce(r.trend, 'sem_regime') as trend, coalesce(r.vol, 'sem_regime') as vol
    from pop p
    left join reg r on p.entry_ts >= r.start_time and p.entry_ts < r.end_time
)
select version, coorte, trend, vol, count(*) n,
       round(avg(r_net), 3) liquido,
       round(sum(r_net), 2) soma_r,
       round(100.0 * count(*) filter (where result = 'target') / count(*), 1) acerto
  from j
 group by 1, 2, 3, 4
having count(*) >= 5   -- celulas com menos de cinco desfechos nao sao lidas
 order by 1, 2, 3, 4;

\echo ''
\echo '== 3. marginais: so a tendencia (a celula cruzada fica rala) =='
with pop as (
  select o.signal_id, s.key || ' ' || sv.version as version,
         case when o.meta ->> 'cohort' like 'replay:%'
              then 'replay:' || left(split_part(o.meta ->> 'cohort', ':', 2), 8)
              else 'prospective' end as coorte,
         o.result, o.r_multiple as r_net, o.entry_ts
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
   where o.tracking_state = 'terminal' and o.r_multiple is not null
), reg as (
  select start_time, end_time,
         supporting_features ->> 'trend' as trend,
         supporting_features ->> 'vol_regime' as vol
    from market_regimes
   where scope = 'btc' and classifier_version like 'regime_hourly_v1%'
), j as (
  select p.*, coalesce(r.trend, 'sem_regime') as trend, coalesce(r.vol, 'sem_regime') as vol
    from pop p left join reg r on p.entry_ts >= r.start_time and p.entry_ts < r.end_time
)
select version, coorte, trend, count(*) n,
       round(avg(r_net), 3) liquido, round(sum(r_net), 2) soma_r,
       round(100.0 * count(*) filter (where result = 'target') / count(*), 1) acerto
  from j group by 1, 2, 3 order by 1, 2, 3;

\echo ''
\echo '== 3b. marginais: so o balde de volatilidade =='
with pop as (
  select o.signal_id, s.key || ' ' || sv.version as version,
         case when o.meta ->> 'cohort' like 'replay:%'
              then 'replay:' || left(split_part(o.meta ->> 'cohort', ':', 2), 8)
              else 'prospective' end as coorte,
         o.result, o.r_multiple as r_net, o.entry_ts
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
   where o.tracking_state = 'terminal' and o.r_multiple is not null
), reg as (
  select start_time, end_time, supporting_features ->> 'vol_regime' as vol
    from market_regimes
   where scope = 'btc' and classifier_version like 'regime_hourly_v1%'
), j as (
  select p.*, coalesce(r.vol, 'sem_regime') as vol
    from pop p left join reg r on p.entry_ts >= r.start_time and p.entry_ts < r.end_time
)
select version, coorte, vol, count(*) n,
       round(avg(r_net), 3) liquido, round(sum(r_net), 2) soma_r,
       round(100.0 * count(*) filter (where result = 'target') / count(*), 1) acerto
  from j group by 1, 2, 3 order by 1, 2, 3;

\echo ''
\echo '== 4. por faixa de score_0_100 do regime na hora da entrada =='
-- O score e o resumo ponderado das cinco componentes (tendencia, breadth,
-- volatilidade, drawdown, funding). Faixas de 20 pontos, declaradas aqui.
with pop as (
  select o.signal_id, s.key || ' ' || sv.version as version,
         case when o.meta ->> 'cohort' like 'replay:%'
              then 'replay:' || left(split_part(o.meta ->> 'cohort', ':', 2), 8)
              else 'prospective' end as coorte,
         o.result, o.r_multiple as r_net, o.entry_ts
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
   where o.tracking_state = 'terminal' and o.r_multiple is not null
), reg as (
  select start_time, end_time, (supporting_features ->> 'score_0_100')::numeric as score
    from market_regimes
   where scope = 'btc' and classifier_version like 'regime_hourly_v1%'
), j as (
  select p.*, r.score
    from pop p left join reg r on p.entry_ts >= r.start_time and p.entry_ts < r.end_time
)
select version, coorte,
       case when score is null then 'sem_score'
            else lpad((floor(score / 20) * 20)::int::text, 3, ' ') || '-'
                 || ((floor(score / 20) * 20)::int + 19)::text end as faixa,
       count(*) n, round(avg(r_net), 3) liquido, round(sum(r_net), 2) soma_r,
       round(100.0 * count(*) filter (where result = 'target') / count(*), 1) acerto
  from j group by 1, 2, 3 order by 1, 2, 3;

\echo ''
\echo '== 5. sanidade: sinais sem hora de regime (a serie tem buraco ali) =='
with pop as (
  select o.signal_id, o.entry_ts
    from signal_outcomes o
   where o.tracking_state = 'terminal' and o.r_multiple is not null
), reg as (
  select start_time, end_time from market_regimes
   where scope = 'btc' and classifier_version like 'regime_hourly_v1%'
)
select count(*) filter (where r.start_time is null) sem_regime,
       count(*) total,
       min(p.entry_ts) filter (where r.start_time is null) primeiro_sem,
       max(p.entry_ts) filter (where r.start_time is null) ultimo_sem
  from pop p left join reg r on p.entry_ts >= r.start_time and p.entry_ts < r.end_time;
