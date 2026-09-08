-- T3.32 item 5 — regime. Duas partes:
--  (a) o que o banco tem de `market_regimes` (o classificador do §4 do PIPELINE);
--  (b) regime reconstruído das velas do BTC (tendência 1 h e vol realizada 1 h),
--      porque `market_regimes` não tem série. Só há velas BTC desde 2026-08-21 20:32Z,
--      então a fatia coberta é declarada na própria tabela (coluna n).
\pset border 2
\pset numericlocale off
\echo '== 7a. o que market_regimes tem =='
select regime, count(*) n, min(start_time) de, max(start_time) ate from market_regimes group by 1;
select count(distinct regime_id) regimes_distintos_referenciados,
       count(*) filter (where regime_id is not null) sinais_com_regime,
       count(*) sinais_total
from agent_signals;
\echo ''
\echo '== 7b. tendencia do BTC na hora anterior a entrada (velas 1m is_final) =='
with btc as (
  select c.open_time, c.close
  from candles c join markets m on m.id=c.market_id
  where m.symbol='BTCUSDT' and m.market_type='perpetual' and c.timeframe='1m' and c.is_final
), pop as (
  select o.signal_id, s.key||' '||sv.version as version,
         case when o.meta->>'cohort' like 'replay:%' then 'replay:'||left(split_part(o.meta->>'cohort',':',2),8)
              else 'prospective' end as coorte,
         o.result, o.r_multiple as r_net, date_trunc('minute', o.entry_ts) as t0
  from signal_outcomes o
  join agent_signals a on a.id=o.signal_id
  join strategy_versions sv on sv.id=a.strategy_version_id
  join strategies s on s.id=sv.strategy_id
  where a.emitted_at < timestamptz '2026-09-08 15:00:00+00'  -- corte declarado da leitura
    and o.tracking_state='terminal' and o.r_multiple is not null
), v as (
  select p.*, b1.close as btc_now, b0.close as btc_1h
  from pop p
  left join btc b1 on b1.open_time = p.t0
  left join btc b0 on b0.open_time = p.t0 - interval '60 min'
), c as (
  select *, case when btc_1h is null or btc_now is null then 'sem_vela_btc'
                 when btc_now/btc_1h - 1 >  0.0015 then 'BTC sobe (>+0,15%)'
                 when btc_now/btc_1h - 1 < -0.0015 then 'BTC cai (<-0,15%)'
                 else 'BTC lateral' end as tendencia
  from v
)
select version, coorte, tendencia, count(*) n,
       round(avg(r_net),3) liquido, round(sum(r_net),2) soma_r,
       round(100.0*count(*) filter (where result='target')/count(*),1) acerto
from c
where (version,coorte) in (('momentum v2','prospective'),('momentum v2','replay:f8d8279c'),
                           ('volume_anomaly v2','prospective'),('volume_anomaly v2','replay:bac27c12'))
group by 1,2,3 order by 1,2,3;
\echo ''
\echo '== 7c. tercil de vol realizada do BTC (1 h antes da entrada) =='
with btc as (
  select c.open_time, c.close from candles c join markets m on m.id=c.market_id
  where m.symbol='BTCUSDT' and m.market_type='perpetual' and c.timeframe='1m' and c.is_final
), pop as (
  select o.signal_id, s.key||' '||sv.version as version,
         case when o.meta->>'cohort' like 'replay:%' then 'replay:'||left(split_part(o.meta->>'cohort',':',2),8)
              else 'prospective' end as coorte,
         o.result, o.r_multiple as r_net, date_trunc('minute', o.entry_ts) as t0
  from signal_outcomes o
  join agent_signals a on a.id=o.signal_id
  join strategy_versions sv on sv.id=a.strategy_version_id
  join strategies s on s.id=sv.strategy_id
  where a.emitted_at < timestamptz '2026-09-08 15:00:00+00'  -- corte declarado da leitura
    and o.tracking_state='terminal' and o.r_multiple is not null
), v as (
  select p.*, (select stddev_samp(r.lr) from (
             select ln(b.close/lag(b.close) over (order by b.open_time)) as lr
             from btc b where b.open_time > p.t0 - interval '60 min' and b.open_time <= p.t0
          ) r) as btc_vol_1h
  from pop p
), t as (
  select *, ntile(3) over (partition by version,coorte order by btc_vol_1h) as tercil
  from v where btc_vol_1h is not null
    and (version,coorte) in (('momentum v2','prospective'),('momentum v2','replay:f8d8279c'),
                             ('volume_anomaly v2','prospective'),('volume_anomaly v2','replay:bac27c12'))
)
select version, coorte, tercil, count(*) n,
       round(100*min(btc_vol_1h),4) vol_min_pct, round(100*max(btc_vol_1h),4) vol_max_pct,
       round(avg(r_net),3) liquido, round(sum(r_net),2) soma_r,
       round(100.0*count(*) filter (where result='target')/count(*),1) acerto
from t group by 1,2,3 order by 1,2,3;
