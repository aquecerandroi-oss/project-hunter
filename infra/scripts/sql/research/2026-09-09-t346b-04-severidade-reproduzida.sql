-- T3.46b — reproduz o detector em SQL sobre as 24 h de feature_snapshots e as baselines
-- realmente selecionaveis, para dizer quantas vezes cada detector CHEGARIA a severidade 40.
begin transaction isolation level repeatable read read only;
\pset border 2

\echo '== 0. o bloco normalization da v2 ativa =='
select version, weights -> 'normalization' as normalization from opportunity_weights where is_active;

\echo '== 1. reproducao: severidade por feature nas ultimas 24 h =='
with params as (
  select (weights->'normalization'->>'deadband_mad')::numeric  as deadband,
         (weights->'normalization'->>'saturation_mad')::numeric as saturation,
         (weights->'normalization'->>'saturation_score')::numeric as sat_score,
         (weights->'baseline_gate'->>'min_distinct_days')::int as min_days,
         (weights->'baseline_gate'->>'min_valid_observations')::int as min_obs
  from opportunity_weights where is_active
),
spec(feature, side) as (
  values ('orderbook_imbalance_20','both'), ('trade_velocity_1m','up'),
         ('open_interest_change_1h','up'), ('relative_volume_5m','up'),
         ('atr_14_pct','up'), ('momentum_15m','both'), ('momentum_acceleration','both')
),
obs as (
  select s.market_id, s.ts, extract(hour from s.ts at time zone 'UTC')::int as hod,
         spec.feature, spec.side,
         (s.features->'values'->spec.feature->>'value')::numeric as x
  from feature_snapshots s
  cross join spec
  where s.ts >= now() - interval '24 hours'
    and s.features->'values'->spec.feature->>'quality' = 'ok'
),
base as (
  select distinct on (market_id, feature, hour_of_day)
         market_id, feature, hour_of_day, median, mad, sample_size, distinct_days, window_end, available_at
  from feature_baselines
  where algo_version = 'median_mad_v1' and sampling = 'per_minute'
    and feature in (select feature from spec)
  order by market_id, feature, hour_of_day, available_at desc, window_end desc, id desc
),
joined as (
  select o.*, b.median, b.mad, b.sample_size, b.distinct_days,
         case when b.market_id is null then 'no_baseline'
              when b.distinct_days < p.min_days or b.sample_size < p.min_obs then 'insufficient_history'
              when b.mad = 0 and o.x <> b.median then 'mad_zero'
              else 'ok' end as verdict,
         case when b.mad > 0 then (o.x - b.median) / b.mad
              when b.mad = 0 and o.x = b.median then 0 end as dev
  from obs o
  cross join params p
  left join base b on b.market_id = o.market_id and b.feature = o.feature and b.hour_of_day = o.hod
),
sev as (
  select j.*, 
         case j.side when 'up' then greatest(j.dev, 0)
                     when 'down' then greatest(-j.dev, 0)
                     else abs(j.dev) end as magnitude
  from joined j where j.verdict = 'ok'
),
scored as (
  select s.feature, s.market_id, s.magnitude,
         case when s.magnitude <= p.deadband then 0
              when s.magnitude >= p.saturation then p.sat_score
              else (s.magnitude - p.deadband) / (p.saturation - p.deadband) * p.sat_score end as severity
  from sev s cross join params p
)
select j.feature,
       count(*) as avaliacoes,
       count(*) filter (where j.verdict = 'ok') as com_baseline_usavel,
       count(*) filter (where j.verdict = 'no_baseline') as sem_baseline,
       count(*) filter (where j.verdict = 'insufficient_history') as baseline_imatura,
       count(*) filter (where j.verdict = 'mad_zero') as mad_zero
from joined j group by 1 order by 1;

\echo '== 2. das avaliacoes com baseline usavel: quantas passariam de 40 (fire) e 20 (hold) =='
with params as (
  select (weights->'normalization'->>'deadband_mad')::numeric  as deadband,
         (weights->'normalization'->>'saturation_mad')::numeric as saturation,
         (weights->'normalization'->>'saturation_score')::numeric as sat_score,
         (weights->'baseline_gate'->>'min_distinct_days')::int as min_days,
         (weights->'baseline_gate'->>'min_valid_observations')::int as min_obs
  from opportunity_weights where is_active
),
spec(feature, side) as (
  values ('orderbook_imbalance_20','both'), ('trade_velocity_1m','up'),
         ('open_interest_change_1h','up'), ('relative_volume_5m','up'),
         ('atr_14_pct','up'), ('momentum_15m','both'), ('momentum_acceleration','both')
),
obs as (
  select s.market_id, s.ts, extract(hour from s.ts at time zone 'UTC')::int as hod,
         spec.feature, spec.side,
         (s.features->'values'->spec.feature->>'value')::numeric as x
  from feature_snapshots s cross join spec
  where s.ts >= now() - interval '24 hours'
    and s.features->'values'->spec.feature->>'quality' = 'ok'
),
base as (
  select distinct on (market_id, feature, hour_of_day)
         market_id, feature, hour_of_day, median, mad, sample_size, distinct_days
  from feature_baselines
  where algo_version = 'median_mad_v1' and sampling = 'per_minute'
    and feature in (select feature from spec)
  order by market_id, feature, hour_of_day, available_at desc, window_end desc, id desc
),
sev as (
  select o.feature, o.market_id, o.ts,
         case o.side when 'up' then greatest((o.x - b.median)/b.mad, 0)
                     when 'down' then greatest(-(o.x - b.median)/b.mad, 0)
                     else abs((o.x - b.median)/b.mad) end as magnitude
  from obs o
  join base b on b.market_id = o.market_id and b.feature = o.feature and b.hour_of_day = o.hod
  cross join params p
  where b.distinct_days >= p.min_days and b.sample_size >= p.min_obs and b.mad > 0
),
scored as (
  select s.feature, s.market_id, s.ts,
         case when s.magnitude <= p.deadband then 0
              when s.magnitude >= p.saturation then p.sat_score
              else (s.magnitude - p.deadband)/(p.saturation - p.deadband) * p.sat_score end as severity
  from sev s cross join params p
)
select feature, count(*) n, count(distinct market_id) mercados,
       round(avg(severity), 2) sev_media,
       round(percentile_cont(0.5) within group (order by severity)::numeric, 2) sev_p50,
       round(percentile_cont(0.99) within group (order by severity)::numeric, 2) sev_p99,
       round(max(severity), 2) sev_max,
       count(*) filter (where severity >= 40) as fires,
       count(*) filter (where severity >= 20) as holds,
       count(distinct market_id) filter (where severity >= 40) as mercados_com_fire
from scored group by 1 order by 1;

commit;
