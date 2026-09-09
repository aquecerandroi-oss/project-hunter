-- T3.46b — o livro alcanca o portao? taxa de disponibilidade e extrapolacao honesta.
begin transaction isolation level repeatable read read only;
\pset border 2
\echo '== 1. janela de feature_snapshots realmente preenchida =='
select min(ts) primeira, max(ts) ultima,
       round(extract(epoch from (max(ts)-min(ts)))/86400.0, 2) as dias_de_serie
from feature_snapshots;

\echo '== 2. disponibilidade de orderbook_imbalance_20 por mercado (24 h) =='
with r as (select market_id, features->'values'->'orderbook_imbalance_20'->>'quality' q
           from feature_snapshots where ts >= now() - interval '24 hours')
select round(100.0*count(*) filter (where q='ok')/count(*), 2) as pct_ok_global,
       count(distinct market_id) filter (where q='ok') as mercados_com_algum_ok,
       count(distinct market_id) as mercados
from r;

\echo '== 3. por mercado: taxa de ok e o sample_size maximo ja alcancado =='
with r as (select market_id, features->'values'->'orderbook_imbalance_20'->>'quality' q
           from feature_snapshots where ts >= now() - interval '24 hours'),
     taxa as (select market_id, 100.0*count(*) filter (where q='ok')/count(*) pct from r group by 1),
     b as (select market_id, max(sample_size) s_max from feature_baselines
           where feature='orderbook_imbalance_20' group by 1)
select width_bucket(t.pct, 0, 100, 10) faixa_pct,
       count(*) mercados, round(min(t.pct),1) pct_min, round(max(t.pct),1) pct_max,
       max(b.s_max) sample_max, round(avg(b.s_max)) sample_medio
from taxa t left join b on b.market_id = t.market_id
group by 1 order by 1;

\echo '== 4. quantos buckets de livro passariam do portao se a taxa de hoje valer 7 dias =='
with b as (select market_id, hour_of_day, sample_size from feature_baselines
           where feature='orderbook_imbalance_20'),
     s as (select round(extract(epoch from (max(ts)-min(ts)))/86400.0, 4) dias from feature_snapshots)
select count(*) buckets,
       count(*) filter (where sample_size >= 120) as passam_hoje,
       count(*) filter (where sample_size * (7.0/s.dias) >= 120) as passariam_em_7d,
       count(distinct market_id) filter (where sample_size * (7.0/s.dias) >= 120) as mercados_em_7d
from b cross join s;

\echo '== 5. o mesmo para trade_velocity_1m e open_interest_change_1h (controle) =='
with b as (select feature, market_id, sample_size from feature_baselines
           where feature in ('trade_velocity_1m','open_interest_change_1h','relative_volume_5m')),
     s as (select round(extract(epoch from (max(ts)-min(ts)))/86400.0, 4) dias from feature_snapshots)
select b.feature, count(*) buckets,
       count(*) filter (where sample_size >= 120) passam_hoje,
       count(*) filter (where sample_size * (7.0/s.dias) >= 120) passariam_em_7d
from b cross join s group by 1 order by 1;
commit;
