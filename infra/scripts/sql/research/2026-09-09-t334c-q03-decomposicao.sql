-- =====================================================================================
-- T3.34c q03 — decomposicao obrigatoria do dia um (EXP-0016, C4 e K6)
--   1. por DECIL de `line_slope_per_bar`, normalizado por ATR (o substituto de regime)
--   2. por MODO x MERCADO (a regra dos 60 %)
--   3. a identidade do pedagio, medida contra o teto declarado de 0,1333 R
--   4. R por dia (bloco), com o intervalo t de 95 % — a regra da KB-0010
--   5. MFE capturado, com a advertencia de `ambiguous` da T3.32
-- coorte `replay:d78c14d1-b4c5-424a-8f31-a43100744bb4` · SOMENTE LEITURA
--
-- `slope` e preco por barra, entao NAO e comparavel entre ETH (~2300) e DOGE (~0,09):
-- toda leitura de inclinacao aqui e `slope / atr` (inclinacao em ATR por barra).
-- Decis de 47 linhas tem 4 a 5 elementos cada: e a decomposicao que o EXP pre-registrou,
-- e o tamanho dela e a resposta honesta sobre o que ela pode dizer.
-- =====================================================================================
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;

-- 1. decis de inclinacao (slope/ATR por barra)
with pop as (
select m.symbol,
       (o.meta->'entry_plan'->>'source_bar_close')::timestamptz            as bar,
       o.result::text                                                     as motivo,
       o.tracking_state::text                                             as estado,
       o.r_multiple                                                       as r_net,
       (o.meta->>'r_ex_funding')::numeric                                  as r_exf,
       (o.meta->'progress'->>'entry')::numeric                             as p_entry,
       (o.meta->'progress'->>'exit_base')::numeric                         as exit_base,
       (o.meta->'excursions'->>'initial_risk')::numeric                    as risk,
       (o.meta->'excursions'->>'mfe')::numeric                             as mfe_px,
       (o.meta->'excursions'->>'ambiguous')::boolean                       as mfe_ambiguo,
       (a.supporting_features->'atr'->>'percent')::numeric                 as atr_pct,
       (a.supporting_features->'atr'->>'value')::numeric                   as atr,
       f.event_kind, f.line_kind,
       f.line_touches::int                                                 as touches,
       f.line_violations::int                                              as violations,
       f.line_slope_per_bar::numeric                                       as slope,
       f.line_first_idx::int                                               as first_idx,
       f.line_last_idx::int                                                as last_idx,
       f.line_valid_from_idx::int                                          as valid_from_idx,
       f.line_price_at_decision::numeric                                   as line_px,
       f.pivot_low_price::numeric                                          as pivot_low,
       f.pivot_low_idx::int                                                as pivot_low_idx,
       f.pattern_pivots::int                                               as pivots,
       f.pattern_lines::int                                                as lines,
       f.pattern_retired_lines::int                                        as retired,
       f.channel_width_atr::numeric                                        as canal_atr,
       f.event_distance_atr::numeric                                       as dist_atr,
       f.relative_volume_15m::numeric                                      as rvol,
       f.close_15m::numeric                                                as close_15m,
       f.line_id
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  join markets m       on m.id = a.market_id
  cross join lateral (
      select jsonb_object_agg(e->>'name', e->>'value') as j
        from jsonb_array_elements(a.supporting_features->'features') e
  ) agg
  cross join lateral jsonb_to_record(agg.j) as f(
      event_kind text, line_kind text, line_touches text, line_violations text,
      line_slope_per_bar text, line_first_idx text, line_last_idx text,
      line_valid_from_idx text, line_price_at_decision text, pivot_low_price text,
      pivot_low_idx text, pattern_pivots text, pattern_lines text,
      pattern_retired_lines text, channel_width_atr text, event_distance_atr text,
      relative_volume_15m text, close_15m text, line_id text)
 where o.meta->>'cohort' = 'replay:d78c14d1-b4c5-424a-8f31-a43100744bb4'
)
, d as (select *, slope/nullif(atr,0) as slope_atr from pop)
   , q as (select *, ntile(10) over (order by slope/nullif(atr,0)) as decil from d)
select decil, count(*) as n,
       round(min(slope_atr), 6) as slope_atr_min,
       round(max(slope_atr), 6) as slope_atr_max,
       round(avg(r_net), 4) as r_liq_medio, round(sum(r_net), 2) as r_liq_soma,
       round(avg((exit_base - p_entry/1.0006)/risk), 4) as r_bruto_medio,
       count(*) filter (where event_kind='bounce') as repiques,
       count(*) filter (where event_kind='breakout') as rompimentos,
       count(*) filter (where motivo='target') as alvos,
       count(*) filter (where motivo='invalidated') as invalidados
  from q group by 1 order by 1;

-- 1b. a mesma coisa em tres faixas de sinal, que e o que 47 linhas sustentam
with pop as (
select m.symbol,
       (o.meta->'entry_plan'->>'source_bar_close')::timestamptz            as bar,
       o.result::text                                                     as motivo,
       o.tracking_state::text                                             as estado,
       o.r_multiple                                                       as r_net,
       (o.meta->>'r_ex_funding')::numeric                                  as r_exf,
       (o.meta->'progress'->>'entry')::numeric                             as p_entry,
       (o.meta->'progress'->>'exit_base')::numeric                         as exit_base,
       (o.meta->'excursions'->>'initial_risk')::numeric                    as risk,
       (o.meta->'excursions'->>'mfe')::numeric                             as mfe_px,
       (o.meta->'excursions'->>'ambiguous')::boolean                       as mfe_ambiguo,
       (a.supporting_features->'atr'->>'percent')::numeric                 as atr_pct,
       (a.supporting_features->'atr'->>'value')::numeric                   as atr,
       f.event_kind, f.line_kind,
       f.line_touches::int                                                 as touches,
       f.line_violations::int                                              as violations,
       f.line_slope_per_bar::numeric                                       as slope,
       f.line_first_idx::int                                               as first_idx,
       f.line_last_idx::int                                                as last_idx,
       f.line_valid_from_idx::int                                          as valid_from_idx,
       f.line_price_at_decision::numeric                                   as line_px,
       f.pivot_low_price::numeric                                          as pivot_low,
       f.pivot_low_idx::int                                                as pivot_low_idx,
       f.pattern_pivots::int                                               as pivots,
       f.pattern_lines::int                                                as lines,
       f.pattern_retired_lines::int                                        as retired,
       f.channel_width_atr::numeric                                        as canal_atr,
       f.event_distance_atr::numeric                                       as dist_atr,
       f.relative_volume_15m::numeric                                      as rvol,
       f.close_15m::numeric                                                as close_15m,
       f.line_id
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  join markets m       on m.id = a.market_id
  cross join lateral (
      select jsonb_object_agg(e->>'name', e->>'value') as j
        from jsonb_array_elements(a.supporting_features->'features') e
  ) agg
  cross join lateral jsonb_to_record(agg.j) as f(
      event_kind text, line_kind text, line_touches text, line_violations text,
      line_slope_per_bar text, line_first_idx text, line_last_idx text,
      line_valid_from_idx text, line_price_at_decision text, pivot_low_price text,
      pivot_low_idx text, pattern_pivots text, pattern_lines text,
      pattern_retired_lines text, channel_width_atr text, event_distance_atr text,
      relative_volume_15m text, close_15m text, line_id text)
 where o.meta->>'cohort' = 'replay:d78c14d1-b4c5-424a-8f31-a43100744bb4'
)
, d as (select *, slope/nullif(atr,0) as slope_atr from pop)
select case when slope/nullif(atr,0) < -0.02 then 'A descendente (< -0,02 ATR/barra)'
            when slope/nullif(atr,0) <  0.02 then 'B quase horizontal ([-0,02; 0,02])'
            else                                  'C ascendente (> 0,02 ATR/barra)' end as faixa,
       count(*) as n,
       round(avg(slope/nullif(atr,0)), 5) as slope_atr_medio,
       round(avg(r_net), 4) as r_liq_medio, round(sum(r_net), 2) as r_liq_soma,
       round(avg((exit_base - p_entry/1.0006)/risk), 4) as r_bruto_medio,
       count(*) filter (where event_kind='bounce') as repiques,
       count(*) filter (where event_kind='breakout') as rompimentos
  from d group by 1 order by 1;

-- 2. modo x mercado (a regra dos 60 % nas duas dimensoes ao mesmo tempo)
with pop as (
select m.symbol,
       (o.meta->'entry_plan'->>'source_bar_close')::timestamptz            as bar,
       o.result::text                                                     as motivo,
       o.tracking_state::text                                             as estado,
       o.r_multiple                                                       as r_net,
       (o.meta->>'r_ex_funding')::numeric                                  as r_exf,
       (o.meta->'progress'->>'entry')::numeric                             as p_entry,
       (o.meta->'progress'->>'exit_base')::numeric                         as exit_base,
       (o.meta->'excursions'->>'initial_risk')::numeric                    as risk,
       (o.meta->'excursions'->>'mfe')::numeric                             as mfe_px,
       (o.meta->'excursions'->>'ambiguous')::boolean                       as mfe_ambiguo,
       (a.supporting_features->'atr'->>'percent')::numeric                 as atr_pct,
       (a.supporting_features->'atr'->>'value')::numeric                   as atr,
       f.event_kind, f.line_kind,
       f.line_touches::int                                                 as touches,
       f.line_violations::int                                              as violations,
       f.line_slope_per_bar::numeric                                       as slope,
       f.line_first_idx::int                                               as first_idx,
       f.line_last_idx::int                                                as last_idx,
       f.line_valid_from_idx::int                                          as valid_from_idx,
       f.line_price_at_decision::numeric                                   as line_px,
       f.pivot_low_price::numeric                                          as pivot_low,
       f.pivot_low_idx::int                                                as pivot_low_idx,
       f.pattern_pivots::int                                               as pivots,
       f.pattern_lines::int                                                as lines,
       f.pattern_retired_lines::int                                        as retired,
       f.channel_width_atr::numeric                                        as canal_atr,
       f.event_distance_atr::numeric                                       as dist_atr,
       f.relative_volume_15m::numeric                                      as rvol,
       f.close_15m::numeric                                                as close_15m,
       f.line_id
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  join markets m       on m.id = a.market_id
  cross join lateral (
      select jsonb_object_agg(e->>'name', e->>'value') as j
        from jsonb_array_elements(a.supporting_features->'features') e
  ) agg
  cross join lateral jsonb_to_record(agg.j) as f(
      event_kind text, line_kind text, line_touches text, line_violations text,
      line_slope_per_bar text, line_first_idx text, line_last_idx text,
      line_valid_from_idx text, line_price_at_decision text, pivot_low_price text,
      pivot_low_idx text, pattern_pivots text, pattern_lines text,
      pattern_retired_lines text, channel_width_atr text, event_distance_atr text,
      relative_volume_15m text, close_15m text, line_id text)
 where o.meta->>'cohort' = 'replay:d78c14d1-b4c5-424a-8f31-a43100744bb4'
)
select event_kind, symbol, count(*) as n,
       round(100.0*count(*)/sum(count(*)) over (), 1) as pct_do_total,
       round(avg(r_net), 4) as r_liq_medio, round(sum(r_net), 2) as r_liq_soma,
       count(distinct bar::date) as dias
  from pop group by 1,2 order by 3 desc;

-- 3. a identidade do pedagio: custo_R medido vs 0,0020/(risco_atr x ATR%)
with pop as (
select m.symbol,
       (o.meta->'entry_plan'->>'source_bar_close')::timestamptz            as bar,
       o.result::text                                                     as motivo,
       o.tracking_state::text                                             as estado,
       o.r_multiple                                                       as r_net,
       (o.meta->>'r_ex_funding')::numeric                                  as r_exf,
       (o.meta->'progress'->>'entry')::numeric                             as p_entry,
       (o.meta->'progress'->>'exit_base')::numeric                         as exit_base,
       (o.meta->'excursions'->>'initial_risk')::numeric                    as risk,
       (o.meta->'excursions'->>'mfe')::numeric                             as mfe_px,
       (o.meta->'excursions'->>'ambiguous')::boolean                       as mfe_ambiguo,
       (a.supporting_features->'atr'->>'percent')::numeric                 as atr_pct,
       (a.supporting_features->'atr'->>'value')::numeric                   as atr,
       f.event_kind, f.line_kind,
       f.line_touches::int                                                 as touches,
       f.line_violations::int                                              as violations,
       f.line_slope_per_bar::numeric                                       as slope,
       f.line_first_idx::int                                               as first_idx,
       f.line_last_idx::int                                                as last_idx,
       f.line_valid_from_idx::int                                          as valid_from_idx,
       f.line_price_at_decision::numeric                                   as line_px,
       f.pivot_low_price::numeric                                          as pivot_low,
       f.pivot_low_idx::int                                                as pivot_low_idx,
       f.pattern_pivots::int                                               as pivots,
       f.pattern_lines::int                                                as lines,
       f.pattern_retired_lines::int                                        as retired,
       f.channel_width_atr::numeric                                        as canal_atr,
       f.event_distance_atr::numeric                                       as dist_atr,
       f.relative_volume_15m::numeric                                      as rvol,
       f.close_15m::numeric                                                as close_15m,
       f.line_id
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  join markets m       on m.id = a.market_id
  cross join lateral (
      select jsonb_object_agg(e->>'name', e->>'value') as j
        from jsonb_array_elements(a.supporting_features->'features') e
  ) agg
  cross join lateral jsonb_to_record(agg.j) as f(
      event_kind text, line_kind text, line_touches text, line_violations text,
      line_slope_per_bar text, line_first_idx text, line_last_idx text,
      line_valid_from_idx text, line_price_at_decision text, pivot_low_price text,
      pivot_low_idx text, pattern_pivots text, pattern_lines text,
      pattern_retired_lines text, channel_width_atr text, event_distance_atr text,
      relative_volume_15m text, close_15m text, line_id text)
 where o.meta->>'cohort' = 'replay:d78c14d1-b4c5-424a-8f31-a43100744bb4'
)
select count(*) as n,
       round(avg(risk/nullif(atr,0)), 4)                                  as risco_atr_medio,
       round(min(risk/nullif(atr,0)), 4)                                  as risco_atr_min,
       round(max(risk/nullif(atr,0)), 4)                                  as risco_atr_max,
       round(avg(risk/nullif(close_15m,0)), 5)                            as risco_pct_medio,
       round(avg((exit_base - p_entry/1.0006)/risk - r_exf), 4)           as custo_r_medido,
       round(avg(0.0020/nullif(risk/nullif(close_15m,0),0)), 4)           as custo_r_identidade,
       count(*) filter (where (exit_base - p_entry/1.0006)/risk - r_exf > 0.1333) as acima_do_teto_declarado
  from pop;

-- 4. R por dia (bloco) e o intervalo t de 95 % sobre as medias diarias
with pop as (
select m.symbol,
       (o.meta->'entry_plan'->>'source_bar_close')::timestamptz            as bar,
       o.result::text                                                     as motivo,
       o.tracking_state::text                                             as estado,
       o.r_multiple                                                       as r_net,
       (o.meta->>'r_ex_funding')::numeric                                  as r_exf,
       (o.meta->'progress'->>'entry')::numeric                             as p_entry,
       (o.meta->'progress'->>'exit_base')::numeric                         as exit_base,
       (o.meta->'excursions'->>'initial_risk')::numeric                    as risk,
       (o.meta->'excursions'->>'mfe')::numeric                             as mfe_px,
       (o.meta->'excursions'->>'ambiguous')::boolean                       as mfe_ambiguo,
       (a.supporting_features->'atr'->>'percent')::numeric                 as atr_pct,
       (a.supporting_features->'atr'->>'value')::numeric                   as atr,
       f.event_kind, f.line_kind,
       f.line_touches::int                                                 as touches,
       f.line_violations::int                                              as violations,
       f.line_slope_per_bar::numeric                                       as slope,
       f.line_first_idx::int                                               as first_idx,
       f.line_last_idx::int                                                as last_idx,
       f.line_valid_from_idx::int                                          as valid_from_idx,
       f.line_price_at_decision::numeric                                   as line_px,
       f.pivot_low_price::numeric                                          as pivot_low,
       f.pivot_low_idx::int                                                as pivot_low_idx,
       f.pattern_pivots::int                                               as pivots,
       f.pattern_lines::int                                                as lines,
       f.pattern_retired_lines::int                                        as retired,
       f.channel_width_atr::numeric                                        as canal_atr,
       f.event_distance_atr::numeric                                       as dist_atr,
       f.relative_volume_15m::numeric                                      as rvol,
       f.close_15m::numeric                                                as close_15m,
       f.line_id
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  join markets m       on m.id = a.market_id
  cross join lateral (
      select jsonb_object_agg(e->>'name', e->>'value') as j
        from jsonb_array_elements(a.supporting_features->'features') e
  ) agg
  cross join lateral jsonb_to_record(agg.j) as f(
      event_kind text, line_kind text, line_touches text, line_violations text,
      line_slope_per_bar text, line_first_idx text, line_last_idx text,
      line_valid_from_idx text, line_price_at_decision text, pivot_low_price text,
      pivot_low_idx text, pattern_pivots text, pattern_lines text,
      pattern_retired_lines text, channel_width_atr text, event_distance_atr text,
      relative_volume_15m text, close_15m text, line_id text)
 where o.meta->>'cohort' = 'replay:d78c14d1-b4c5-424a-8f31-a43100744bb4'
)
, dia as (select bar::date as d, count(*) as n, avg(r_net) as media from pop
                 where r_net is not null group by 1)
select count(*) as blocos_dia, round(avg(media), 4) as media_das_medias_diarias,
       round(stddev_samp(media), 4) as desvio,
       round((stddev_samp(media)/sqrt(count(*)))::numeric, 4) as erro_padrao,
       round((avg(media) - 2.160*stddev_samp(media)/sqrt(count(*)))::numeric, 4) as ic95_inferior,
       round((avg(media) + 2.160*stddev_samp(media)/sqrt(count(*)))::numeric, 4) as ic95_superior,
       count(*) filter (where media > 0) as dias_positivos,
       count(*) filter (where media < 0) as dias_negativos,
       max(n) as maior_dia
  from dia;

-- 5. MFE capturado (limite inferior quando `ambiguous`, T3.32 CONCERN)
with pop as (
select m.symbol,
       (o.meta->'entry_plan'->>'source_bar_close')::timestamptz            as bar,
       o.result::text                                                     as motivo,
       o.tracking_state::text                                             as estado,
       o.r_multiple                                                       as r_net,
       (o.meta->>'r_ex_funding')::numeric                                  as r_exf,
       (o.meta->'progress'->>'entry')::numeric                             as p_entry,
       (o.meta->'progress'->>'exit_base')::numeric                         as exit_base,
       (o.meta->'excursions'->>'initial_risk')::numeric                    as risk,
       (o.meta->'excursions'->>'mfe')::numeric                             as mfe_px,
       (o.meta->'excursions'->>'ambiguous')::boolean                       as mfe_ambiguo,
       (a.supporting_features->'atr'->>'percent')::numeric                 as atr_pct,
       (a.supporting_features->'atr'->>'value')::numeric                   as atr,
       f.event_kind, f.line_kind,
       f.line_touches::int                                                 as touches,
       f.line_violations::int                                              as violations,
       f.line_slope_per_bar::numeric                                       as slope,
       f.line_first_idx::int                                               as first_idx,
       f.line_last_idx::int                                                as last_idx,
       f.line_valid_from_idx::int                                          as valid_from_idx,
       f.line_price_at_decision::numeric                                   as line_px,
       f.pivot_low_price::numeric                                          as pivot_low,
       f.pivot_low_idx::int                                                as pivot_low_idx,
       f.pattern_pivots::int                                               as pivots,
       f.pattern_lines::int                                                as lines,
       f.pattern_retired_lines::int                                        as retired,
       f.channel_width_atr::numeric                                        as canal_atr,
       f.event_distance_atr::numeric                                       as dist_atr,
       f.relative_volume_15m::numeric                                      as rvol,
       f.close_15m::numeric                                                as close_15m,
       f.line_id
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  join markets m       on m.id = a.market_id
  cross join lateral (
      select jsonb_object_agg(e->>'name', e->>'value') as j
        from jsonb_array_elements(a.supporting_features->'features') e
  ) agg
  cross join lateral jsonb_to_record(agg.j) as f(
      event_kind text, line_kind text, line_touches text, line_violations text,
      line_slope_per_bar text, line_first_idx text, line_last_idx text,
      line_valid_from_idx text, line_price_at_decision text, pivot_low_price text,
      pivot_low_idx text, pattern_pivots text, pattern_lines text,
      pattern_retired_lines text, channel_width_atr text, event_distance_atr text,
      relative_volume_15m text, close_15m text, line_id text)
 where o.meta->>'cohort' = 'replay:d78c14d1-b4c5-424a-8f31-a43100744bb4'
)
select count(*) as n, count(*) filter (where mfe_ambiguo) as mfe_ambiguos,
       round(avg(mfe_px/risk), 4) as mfe_medio_r,
       round(percentile_cont(0.5) within group (order by mfe_px/risk)::numeric, 4) as mfe_p50_r,
       round(percentile_cont(0.9) within group (order by mfe_px/risk)::numeric, 4) as mfe_p90_r,
       round(avg((exit_base - p_entry/1.0006)/risk), 4) as r_bruto_medio,
       round(100.0*count(*) filter (where mfe_px/risk >= 2.0)/count(*), 1) as pct_mfe_maior_2r,
       round(100.0*count(*) filter (where mfe_px/risk >= 1.0)/count(*), 1) as pct_mfe_maior_1r
  from pop where risk > 0;

commit;
