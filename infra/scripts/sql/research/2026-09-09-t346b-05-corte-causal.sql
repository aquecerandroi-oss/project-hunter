-- T3.46b — a mesma reproducao, mas com o corte causal exato do BaselineProjection:
-- available_at <= observation_ts  E  window_end < observation_ts, escolhendo a revisao vencedora.
begin transaction isolation level repeatable read read only;
\pset border 2
\echo '== 0. corte =='
select now() at time zone 'utc' utc, now() at time zone 'America/Sao_Paulo' brt;

\echo '== 1. feature_version armazenado por feature (mismatch mata a baseline) =='
select feature, feature_version, count(*) from feature_baselines
where feature in ('orderbook_imbalance_20','trade_velocity_1m','open_interest_change_1h','relative_volume_5m')
group by 1,2 order by 1,2;

\echo '== 2. quando cada feature ganhou a PRIMEIRA baseline que passa o gate =='
select feature, source, min(available_at) as primeira_utilizavel, count(*) as buckets
from feature_baselines where distinct_days >= 3 and sample_size >= 120
group by 1,2 order by 3;

\echo '== 3. reproducao sob o corte causal, ultimas 6 h =='
with params as (
  select (weights->'normalization'->>'deadband_mad')::numeric d,
         (weights->'normalization'->>'saturation_mad')::numeric s,
         (weights->'normalization'->>'saturation_score')::numeric sc,
         (weights->'baseline_gate'->>'min_distinct_days')::int md,
         (weights->'baseline_gate'->>'min_valid_observations')::int mo
  from opportunity_weights where is_active
),
spec(feature, side) as (values
  ('orderbook_imbalance_20','both'), ('trade_velocity_1m','up'), ('open_interest_change_1h','up'),
  ('relative_volume_5m','up'), ('atr_14_pct','up'), ('momentum_15m','both'), ('momentum_acceleration','both')),
obs as (
  select s.market_id, s.ts, extract(hour from s.ts at time zone 'UTC')::int hod, spec.feature, spec.side,
         (s.features->'values'->spec.feature->>'value')::numeric x
  from feature_snapshots s cross join spec
  where s.ts >= now() - interval '6 hours'
    and s.features->'values'->spec.feature->>'quality' = 'ok'
),
picked as (
  select distinct on (o.market_id, o.feature, o.ts)
         o.market_id, o.feature, o.side, o.ts, o.x,
         b.median, b.mad, b.sample_size, b.distinct_days
  from obs o
  join feature_baselines b
    on b.market_id = o.market_id and b.feature = o.feature and b.hour_of_day = o.hod
   and b.algo_version = 'median_mad_v1' and b.sampling = 'per_minute'
   and b.feature_version = 1
   and b.available_at <= o.ts and b.window_end < o.ts
  order by o.market_id, o.feature, o.ts, b.available_at desc, b.window_end desc, b.id desc
),
verd as (
  select p.*, case when p.distinct_days < q.md or p.sample_size < q.mo then 'insufficient_history'
                   when p.mad = 0 and p.x <> p.median then 'mad_zero' else 'ok' end v,
         case p.side when 'up' then greatest((p.x-p.median)/nullif(p.mad,0),0)
                     when 'down' then greatest(-(p.x-p.median)/nullif(p.mad,0),0)
                     else abs((p.x-p.median)/nullif(p.mad,0)) end mag
  from picked p cross join params q
),
scored as (
  select v.feature, v.market_id, v.v,
         case when v.mag is null then null
              when v.mag <= q.d then 0
              when v.mag >= q.s then q.sc
              else (v.mag - q.d)/(q.s - q.d)*q.sc end severity
  from verd v cross join params q
)
select feature,
       count(*) as com_baseline,
       count(*) filter (where v='ok') as usavel,
       count(*) filter (where v='insufficient_history') as imatura,
       count(*) filter (where v='mad_zero') as mad_zero,
       count(*) filter (where v='ok' and severity >= 40) as fires,
       count(distinct market_id) filter (where v='ok' and severity >= 40) as mercados_fire,
       round(max(severity) filter (where v='ok'), 2) as sev_max
from scored group by 1 order by 1;

\echo '== 4. anomalias abertas nas ultimas 6 h, por tipo (o que o scanner de fato gravou) =='
select type, count(*) n, count(distinct market_id) mercados, min(detected_at) primeira
from anomalies where detected_at >= now() - interval '6 hours' group by 1 order by 2 desc;

commit;
