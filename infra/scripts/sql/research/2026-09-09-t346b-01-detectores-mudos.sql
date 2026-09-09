-- T3.46b — por que ORDERBOOK_IMBALANCE, OPEN_INTEREST_SPIKE e TRADE_VELOCITY_SPIKE nao emitem.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
\pset border 2
\pset format aligned

\echo '== 0. corte de leitura =='
select now() at time zone 'utc' as read_at_utc, now() at time zone 'America/Sao_Paulo' as read_at_brt;

\echo '== 1. anomalias por tipo (toda a serie) =='
select t.type,
       coalesce(a.n, 0) as linhas,
       coalesce(a.mercados, 0) as mercados,
       a.primeira, a.ultima
from unnest(enum_range(null::anomaly_type)) as t(type)
left join (
  select type, count(*) n, count(distinct market_id) mercados,
         min(detected_at) primeira, max(detected_at) ultima
  from anomalies group by type
) a on a.type = t.type
order by linhas desc, t.type;

\echo '== 2. a feature de cada detector mudo esta sendo calculada? (feature_snapshots, ultima hora) =='
with recent as (
  select market_id, ts, features
  from feature_snapshots
  where ts >= now() - interval '1 hour'
), f(feature) as (
  values ('orderbook_imbalance_20'), ('trade_velocity_1m'), ('open_interest_change_1h'),
         ('relative_volume_5m'), ('atr_14_pct'), ('momentum_15m'), ('funding_rate')
)
select f.feature,
       count(*) filter (where r.features ? f.feature) as com_chave,
       count(*) filter (where r.features -> f.feature ->> 'quality' = 'ok') as ok,
       count(*) filter (where r.features -> f.feature ->> 'quality' = 'degraded') as degraded,
       count(*) filter (where r.features -> f.feature ->> 'quality' = 'unavailable') as unavailable,
       count(distinct r.market_id) filter (where r.features -> f.feature ->> 'quality' = 'ok') as mercados_ok
from f cross join recent r
group by f.feature order by f.feature;

\echo '== 2b. quando indisponivel, qual o motivo (ultima hora) =='
with recent as (
  select features from feature_snapshots where ts >= now() - interval '1 hour'
), f(feature) as (
  values ('orderbook_imbalance_20'), ('trade_velocity_1m'), ('open_interest_change_1h')
)
select f.feature,
       coalesce(r.features -> f.feature ->> 'reason', '(sem motivo)') as motivo,
       count(*) as n
from f cross join recent r
where r.features ? f.feature and r.features -> f.feature ->> 'quality' <> 'ok'
group by 1, 2 order by 1, 3 desc;

\echo '== 3. baselines por feature: existem? passam o gate da v2? =='
select b.feature, b.source, count(*) linhas, count(distinct b.market_id) mercados,
       round(avg(b.sample_size)) amostra_media, round(avg(b.distinct_days), 2) dias_media,
       count(*) filter (where b.distinct_days >= 3 and b.sample_size >= 120) as passam_gate,
       count(*) filter (where b.mad = 0) as mad_zero
from feature_baselines b
where b.feature in ('orderbook_imbalance_20','trade_velocity_1m','open_interest_change_1h',
                    'relative_volume_5m','atr_14_pct','momentum_15m','momentum_acceleration')
group by 1, 2 order by 1, 2;

\echo '== 3b. o gate publicado na opportunity_weights ativa =='
select version, weights -> 'baseline_gate' as baseline_gate
from opportunity_weights where is_active order by version;

\echo '== 4. baselines dos tres mudos: distribuicao de mad e mediana =='
select feature,
       count(*) n,
       count(*) filter (where mad = 0) mad_zero,
       round(avg(mad)::numeric, 8) mad_medio,
       round(avg(median)::numeric, 8) mediana_media,
       round(min(median)::numeric, 8) mediana_min,
       round(max(median)::numeric, 8) mediana_max
from feature_baselines
where feature in ('orderbook_imbalance_20','trade_velocity_1m','open_interest_change_1h')
group by 1 order by 1;

\echo '== 5. quantas features distintas tem baseline, por fonte =='
select source, count(distinct feature) features, string_agg(distinct feature, ', ' order by feature) as lista
from feature_baselines group by source;

commit;
