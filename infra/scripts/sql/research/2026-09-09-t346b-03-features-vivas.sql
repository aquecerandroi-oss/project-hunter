begin transaction isolation level repeatable read read only;
\pset border 2
\echo '== 0. corte =='
select now() at time zone 'utc' read_at_utc, now() at time zone 'America/Sao_Paulo' read_at_brt;

\echo '== 1. qualidade por feature na ultima hora (feature_snapshots -> values) =='
with recent as (select market_id, features->'values' as v from feature_snapshots where ts >= now() - interval '1 hour'),
     f(feature) as (values ('orderbook_imbalance_20'),('trade_velocity_1m'),('open_interest_change_1h'),
                           ('spread_pct'),('buy_pressure_5m'),('relative_volume_5m'),('atr_14_pct'),
                           ('momentum_15m'),('momentum_acceleration'),('funding_rate'))
select f.feature,
       count(*) as linhas,
       count(*) filter (where r.v -> f.feature ->> 'quality' = 'ok') as ok,
       count(*) filter (where r.v -> f.feature ->> 'quality' = 'degraded') as degraded,
       count(*) filter (where r.v -> f.feature ->> 'quality' = 'unavailable') as unavailable,
       count(distinct r.market_id) filter (where r.v -> f.feature ->> 'quality' = 'ok') as mercados_ok
from f cross join recent r group by 1 order by 1;

\echo '== 2. motivo da indisponibilidade, por feature (ultima hora) =='
with recent as (select features->'values' as v from feature_snapshots where ts >= now() - interval '1 hour'),
     f(feature) as (values ('orderbook_imbalance_20'),('trade_velocity_1m'),('open_interest_change_1h'),('spread_pct'))
select f.feature, coalesce(r.v -> f.feature ->> 'reason','(nulo)') motivo, count(*) n
from f cross join recent r
where r.v -> f.feature ->> 'quality' <> 'ok'
group by 1,2 order by 1,3 desc;

\echo '== 3. distribuicao dos valores das tres features mudas (ultima hora, quality=ok) =='
with recent as (select features->'values' as v from feature_snapshots where ts >= now() - interval '1 hour'),
     f(feature) as (values ('orderbook_imbalance_20'),('trade_velocity_1m'),('open_interest_change_1h'))
select f.feature, count(*) n,
       round(min((r.v->f.feature->>'value')::numeric),6) v_min,
       round(percentile_cont(0.5) within group (order by (r.v->f.feature->>'value')::numeric)::numeric,6) v_p50,
       round(percentile_cont(0.99) within group (order by (r.v->f.feature->>'value')::numeric)::numeric,6) v_p99,
       round(max((r.v->f.feature->>'value')::numeric),6) v_max
from f cross join recent r
where r.v -> f.feature ->> 'quality' = 'ok'
group by 1 order by 1;

\echo '== 4. anomalias: chaves do metadata =='
select type, jsonb_object_keys(metadata) k, count(*) from anomalies group by 1,2 order by 1,2 limit 40;

commit;
