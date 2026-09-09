begin transaction isolation level repeatable read read only;
\pset border 2
\echo '== 1. feature_snapshots existe? =='
select count(*) as linhas, min(ts) as primeira, max(ts) as ultima from feature_snapshots;

\echo '== 2. particoes de feature_snapshots =='
select c.relname, pg_get_expr(c.relpartbound, c.oid) as bound
from pg_class c join pg_inherits i on i.inhrelid = c.oid
join pg_class p on p.oid = i.inhparent
where p.relname = 'feature_snapshots' order by 1;

\echo '== 3. baselines dos tres mudos: por que nao passam o gate (sample_size/distinct_days) =='
select feature,
       count(*) n,
       count(*) filter (where distinct_days >= 3) as dias_ok,
       count(*) filter (where sample_size >= 120) as amostra_ok,
       count(*) filter (where distinct_days >= 3 and sample_size >= 120) as ambos,
       min(sample_size) s_min, round(avg(sample_size)) s_avg, max(sample_size) s_max,
       min(distinct_days) d_min, max(distinct_days) d_max,
       max(window_end) as ultima_janela
from feature_baselines
where feature in ('orderbook_imbalance_20','trade_velocity_1m','open_interest_change_1h','relative_volume_5m')
group by 1 order by 1;

\echo '== 4. amostras vivas por feature (baseline_observations existe?) =='
select table_name from information_schema.tables
where table_schema='public' and table_name like '%observation%' order by 1;

\echo '== 5. as anomalias que EXISTEM: qual severidade e desvio no momento de gravar =='
select type,
       count(*) n,
       round(avg((metadata->>'deviation')::numeric), 2) dev_medio,
       round(max((metadata->>'deviation')::numeric), 2) dev_max,
       round(avg((metadata->>'severity')::numeric), 2) sev_meta_media
from anomalies where metadata ? 'deviation' group by 1 order by 2 desc;

\echo '== 6. mercados com baseline utilizavel por feature (gate v2) =='
select feature, count(distinct market_id) as mercados_com_pelo_menos_um_bucket_valido
from feature_baselines
where distinct_days >= 3 and sample_size >= 120
group by 1 order by 2 desc;

\echo '== 7. markets: 217 monitorados x 200 do heartbeat =='
select exchange_id::text, market_type::text, status::text, is_monitored, count(*)
from markets group by 1,2,3,4 order by 1,2,3,4;

\echo '== 7b. is_monitored por exchange com nome =='
select e.code, m.market_type::text, count(*) filter (where m.is_monitored) as monitorados, count(*) as total
from markets m join exchanges e on e.id = m.exchange_id
group by 1,2 order by 1,2;

commit;
