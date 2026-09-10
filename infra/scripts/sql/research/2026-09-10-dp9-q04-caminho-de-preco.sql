-- D-P9 q04 -- O CAMINHO DE PRECO DAS 5 PIORES APOSTAS UNICAS DAS 21Z.
-- Pergunta: a perda veio de UM IMPULSO (uma vela de 1 min maior que 1 ATR) ou
-- de uma DERIVA (muitas velas pequenas na mesma direcao)? A regua e o ATR que a
-- propria decisao usou (`supporting_features->'atr'->>'value'`, wilder_v1 de 15 m,
-- janela terminando na barra da decisao) -- nao um ATR recalculado hoje.
-- As apostas (mercado perpetuo, barra de 15 min, R agrupado das 7-8 versoes):
--   ZKUSDT 21:30Z -8,69 | XVGUSDT 21:00Z -8,43 | PHAUSDT 21:30Z -6,90
--   NEARUSDT 21:30Z -5,27 | NEARUSDT 21:00Z -2,18
-- Velas: `candles_1m` do PERPETUO, apenas `is_final` (nenhuma vela em formacao).
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off

-- 1. resumo por aposta: entrada, pior minuto, e o teste do impulso
with apostas as (
  select mk.id as market_id, mk.symbol,
         date_bin('15 minutes', (a.supporting_features->>'observation_ts')::timestamptz, timestamptz 'epoch') as barra,
         min(o.entry_ts) as entry_ts, max(o.exit_ts) as exit_ts,
         min(o.virtual_entry) as entrada,
         max((a.supporting_features->'atr'->>'value')::numeric) filter (where sv.version = 'v1') as atr_v1,
         avg((a.supporting_features->'atr'->>'value')::numeric) as atr_medio,
         count(*) as decisoes, sum(o.r_multiple) as soma_r
    from signal_outcomes o
    join agent_signals a      on a.id = o.signal_id
    join markets mk           on mk.id = a.market_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
   where o.meta->>'cohort' = 'prospective'
     and mk.market_type = 'perpetual'
     and ( (s.key = 'mean_reversion' and sv.version in ('v1','v2','v3','v6','v7','v8','v10','v14'))
        or (s.key = 'mean_reversion_h1' and sv.version = 'v1') )
     and o.tracking_state = 'terminal'
     and a.emitted_at >= '2026-09-09 21:00:00+00' and a.emitted_at < '2026-09-09 22:00:00+00'
     and mk.symbol in ('ZKUSDT','XVGUSDT','PHAUSDT','NEARUSDT')
   group by 1,2,3
), velas as (
  select ap.symbol, ap.barra, ap.entrada, coalesce(ap.atr_v1, ap.atr_medio) as atr,
         ap.entry_ts, ap.exit_ts, ap.decisoes, ap.soma_r,
         c.open_time, c.open, c.high, c.low, c.close, c.volume
    from apostas ap
    join candles_1m c on c.market_id = ap.market_id
                     and c.is_final
                     and c.open_time >= date_trunc('minute', ap.entry_ts)
                     and c.open_time <= ap.exit_ts
)
select symbol,
       to_char(barra at time zone 'America/Sao_Paulo','HH24:MI') barra_brt,
       decisoes, round(soma_r,3) soma_r,
       round(entrada,8) entrada, round(atr,8) atr,
       round(100*atr/entrada,3) atr_pct,
       count(*) velas_1m,
       round(min(low),8) minima,
       round(100*(min(low)-entrada)/entrada,3) queda_max_pct,
       round((entrada - min(low))/atr,2) queda_max_em_atr,
       round(max(open - close)/atr,2) pior_vela_corpo_atr,
       round(max(high - low)/atr,2) pior_vela_amplitude_atr,
       count(*) filter (where (open - close) > atr) velas_corpo_acima_1atr,
       count(*) filter (where (high - low) > atr) velas_amplitude_acima_1atr,
       count(*) filter (where close < open) velas_de_baixa
  from velas group by symbol, barra, decisoes, soma_r, entrada, atr order by soma_r;

-- 2. o caminho minuto a minuto (ate 80 min depois da entrada, que ja cobre todos
--    os stops desta hora: o mais longo saiu 68 min depois)
with apostas as (
  select mk.id as market_id, mk.symbol,
         date_bin('15 minutes', (a.supporting_features->>'observation_ts')::timestamptz, timestamptz 'epoch') as barra,
         min(o.entry_ts) as entry_ts, max(o.exit_ts) as exit_ts,
         min(o.virtual_entry) as entrada,
         max((a.supporting_features->'atr'->>'value')::numeric) filter (where sv.version = 'v1') as atr_v1,
         avg((a.supporting_features->'atr'->>'value')::numeric) as atr_medio
    from signal_outcomes o
    join agent_signals a      on a.id = o.signal_id
    join markets mk           on mk.id = a.market_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
   where o.meta->>'cohort' = 'prospective'
     and mk.market_type = 'perpetual'
     and ( (s.key = 'mean_reversion' and sv.version in ('v1','v2','v3','v6','v7','v8','v10','v14'))
        or (s.key = 'mean_reversion_h1' and sv.version = 'v1') )
     and o.tracking_state = 'terminal'
     and a.emitted_at >= '2026-09-09 21:00:00+00' and a.emitted_at < '2026-09-09 22:00:00+00'
     and mk.symbol in ('ZKUSDT','XVGUSDT','PHAUSDT','NEARUSDT')
   group by 1,2,3
)
select ap.symbol,
       to_char(ap.barra at time zone 'America/Sao_Paulo','HH24:MI') barra_brt,
       to_char(c.open_time at time zone 'America/Sao_Paulo','HH24:MI') minuto_brt,
       extract(epoch from (c.open_time - date_trunc('minute', ap.entry_ts)))/60 as m,
       c.open, c.high, c.low, c.close,
       round((c.close - c.open)/coalesce(ap.atr_v1, ap.atr_medio),3) as corpo_atr,
       round((c.high - c.low)/coalesce(ap.atr_v1, ap.atr_medio),3) as amplitude_atr,
       round((c.close - ap.entrada)/coalesce(ap.atr_v1, ap.atr_medio),3) as desde_entrada_atr,
       c.volume, c.trade_count
  from apostas ap
  join candles_1m c on c.market_id = ap.market_id and c.is_final
                   and c.open_time >= date_trunc('minute', ap.entry_ts)
                   and c.open_time <= least(ap.exit_ts, ap.entry_ts + interval '80 minutes')
 order by ap.symbol, ap.barra, c.open_time;

commit;
