-- T3.50 Q2 — exportacao SOMENTE LEITURA de uma operacao concluida por linha,
-- em JSON, com as barras de 15 min que o grafico precisa. Consumida por
-- `infra/scripts/render_operations.py export`, que a entrega pelo stdin do psql
-- e le o stdout (nada e escrito na VPS e nada e escrito em disco do servidor).
--
-- VARIAVEIS (psql -v):
--   strategy  chave em `strategies.key`      (ex.: momentum)
--   ver       `strategy_versions.version`     (ex.: v6)
--   coorte    'replay' | 'prospective' | 'all'
--   since     timestamptz minimo da decisao   ('-infinity' para tudo)
--
-- O CORTE DA BARRA DE DECISAO, e por que ele nao antecipa nada:
--   decision_bar_close = date_bin('15 min', observation_ts, 'epoch')
--   -> a ULTIMA barra de 15 min completamente fechada em observation_ts.
--   Para uma versao de 15 min (observation_ts alinhado) e exatamente a barra
--   que a estrategia leu. Para uma de 5 min (volume_anomaly) e a ultima barra
--   de 15 min que ja existia — nunca a que ainda estava se formando.
--
-- JANELA DE VELAS: 96 barras de 15 min terminando NA barra da decisao
--   (`pattern_bars` de trendline_breakout_v1) + o trecho ate a saida + 4 barras
--   de contexto depois dela.
--
-- COMPLETUDE (mesma regra da T3.34 §4): so vela 1 min `is_final`, dobrada por
-- `date_bin` desde a epoca, e o balde so existe com os 15 minutos presentes.
-- Balde incompleto nao e exportado; o renderer usa a corrida CONTIGUA que
-- termina na barra da decisao e declara quantas barras sobraram.
begin transaction isolation level repeatable read read only;

\set ON_ERROR_STOP on

with ops as (
  select o.signal_id,
         m.symbol,
         m.id                                             as market_id,
         e.code                                           as exchange,
         s.key                                            as strategy,
         sv.version                                       as version,
         sv.code_ref                                      as code_ref,
         coalesce(a.supporting_features->>'cohort', o.meta->>'cohort', '')   as cohort,
         case when coalesce(a.supporting_features->>'cohort', o.meta->>'cohort', '')
                   like 'replay:%' then 'replay' else 'prospective' end      as coorte,
         a.direction::text                                as direction,
         coalesce((a.supporting_features->>'observation_ts')::timestamptz,
                  a.emitted_at)                           as observation_ts,
         a.emitted_at                                     as decision_at,
         date_bin('15 minutes',
                  coalesce((a.supporting_features->>'observation_ts')::timestamptz,
                           a.emitted_at),
                  timestamptz 'epoch')                    as decision_bar_close,
         a.reason                                         as reason,
         a.targets                                        as signal_targets,
         a.invalidations                                  as invalidations,
         a.supporting_features                            as supporting_features,
         o.virtual_entry, o.virtual_stop, o.virtual_targets,
         o.entry_ts, o.exit_price, o.exit_ts, o.mfe, o.mae,
         o.r_multiple, o.result::text                     as result,
         o.tracking_state::text                           as tracking_state,
         o.no_entry_reason, o.censored_reason,
         o.meta                                           as outcome_meta
    from signal_outcomes o
    join agent_signals a      on a.id  = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id  = sv.strategy_id
    join markets m            on m.id  = a.market_id
    join exchanges e          on e.id  = m.exchange_id
   where o.tracking_state = 'terminal'
     and o.r_multiple is not null
     and s.key = :'strategy'
     and sv.version = :'ver'
), scoped as (
  select * from ops
   where (:'coorte' = 'all' or coorte = :'coorte')
     and decision_at >= :'since'::timestamptz
), framed as (
  select scoped.*,
         decision_bar_close - interval '15 minutes'                        as decision_bar_open,
         decision_bar_close - interval '15 minutes' - interval '1425 minutes' as win_from,
         date_bin('15 minutes',
                  coalesce(exit_ts, entry_ts, observation_ts),
                  timestamptz 'epoch') + interval '75 minutes'             as win_to
    from scoped
)
select row_to_json(payload)
  from (
    select f.signal_id, f.symbol, f.exchange, f.strategy, f.version, f.code_ref,
           f.cohort, f.coorte, f.direction,
           f.observation_ts, f.decision_at, f.decision_bar_open, f.decision_bar_close,
           f.reason, f.signal_targets, f.invalidations, f.supporting_features,
           f.virtual_entry, f.virtual_stop, f.virtual_targets,
           f.entry_ts, f.exit_price, f.exit_ts, f.mfe, f.mae,
           f.r_multiple, f.result, f.tracking_state, f.no_entry_reason, f.censored_reason,
           f.outcome_meta,
           coalesce(bars.rows, '[]'::json) as bars
      from framed f
      left join lateral (
        select json_agg(json_build_array(
                 to_char(b.bucket at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
                 b.o, b.h, b.l, b.c, b.v, b.minutes) order by b.bucket) as rows
          from (
            select date_bin('15 minutes', c.open_time, timestamptz 'epoch')        as bucket,
                   (array_agg(c.open  order by c.open_time))[1]                    as o,
                   max(c.high)                                                     as h,
                   min(c.low)                                                      as l,
                   (array_agg(c.close order by c.open_time desc))[1]               as c,
                   sum(c.volume)                                                   as v,
                   count(*)                                                        as minutes
              from candles c
             where c.market_id = f.market_id
               and c.timeframe = '1m'
               and c.is_final
               and c.open_time >= f.win_from
               and c.open_time <  f.win_to
             group by 1
            having count(*) = 15
          ) b
      ) bars on true
     order by f.decision_at
  ) payload;

commit;
