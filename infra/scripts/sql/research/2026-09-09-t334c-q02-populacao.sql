-- =====================================================================================
-- T3.34c q02 — a populacao do dia um da `trendline_breakout v1`
-- coorte `replay:d78c14d1-b4c5-424a-8f31-a43100744bb4` · SOMENTE LEITURA
--
-- Metodo: o da notes-T3.40 (q10) e da notes-T3.42, sem uma linha nova de aritmetica.
--   R bruto  = (exit_base - p_entry/1.0006) / risco_inicial   (o 1,0006 e o spread+slippage
--              ja embutido no preco de entrada registrado, identico ao das notas anteriores)
--   custo R  = R bruto - r_ex_funding
--   R liq.   = `signal_outcomes.r_multiple` (o que o Lab acompanhou)
-- `supporting_features.features` e um ARRAY de {name,value}; a extracao e por `name`.
-- =====================================================================================
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;

-- 1. a populacao inteira (K1, K3, K5 e o quadro de expectancy)
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
select count(*)                                                                    as decisoes,
       count(*) filter (where estado='terminal' and r_net is not null)              as avaliaveis,
       count(*) filter (where risk is null or risk<=0)                              as sem_risco,
       round(avg((exit_base - p_entry/1.0006)/risk) filter (where risk>0), 4)        as exp_bruta_r,
       round(avg((exit_base - p_entry/1.0006)/risk - r_exf) filter (where risk>0), 4)as custo_r,
       round(avg(r_net) filter (where r_net is not null), 4)                         as exp_liquida_r,
       round(sum(r_net) filter (where r_net is not null), 2)                         as soma_r,
       round(100.0*count(*) filter (where motivo='target')
             /nullif(count(*) filter (where estado='terminal'),0), 1)                as acerto_pct,
       round(sum(r_net) filter (where r_net>0)
             /nullif(-sum(r_net) filter (where r_net<0),0), 4)                       as pf_liquido,
       count(distinct bar::date)                                                     as dias,
       count(distinct symbol)                                                        as mercados,
       round(min(atr_pct),5) as atr_pct_min_obs, round(max(atr_pct),5) as atr_pct_max_obs
  from pop;

-- 2. motivos de saida
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
select motivo, count(*) as n,
       round(100.0*count(*)/sum(count(*)) over (), 1)                   as pct,
       round(avg(r_net), 4)                                             as r_liq_medio,
       round(sum(r_net), 2)                                             as r_liq_soma,
       round(avg((exit_base - p_entry/1.0006)/risk), 4)                 as r_bruto_medio
  from pop group by 1 order by 2 desc;

-- 3. K6 — concentracao por MERCADO (a regra dos 60 %)
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
select symbol, count(*) as n,
       round(100.0*count(*)/sum(count(*)) over (), 1)                   as pct,
       round(avg(r_net), 4) as r_liq_medio, round(sum(r_net), 2) as r_liq_soma,
       count(distinct bar::date) as dias
  from pop group by 1 order by 2 desc;

-- 4. K6 — concentracao por MODO (rompimento vs repique), a segunda metade da regra
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
select event_kind, line_kind, count(*) as n,
       round(100.0*count(*)/sum(count(*)) over (), 1)                   as pct,
       round(avg(r_net), 4) as r_liq_medio, round(sum(r_net), 2) as r_liq_soma,
       round(avg((exit_base - p_entry/1.0006)/risk), 4) as r_bruto_medio,
       count(distinct bar::date) as dias,
       count(*) filter (where motivo='target') as alvos,
       count(*) filter (where motivo='invalidated') as invalidados,
       count(*) filter (where motivo='stop') as stops,
       count(*) filter (where motivo='expired') as expirados
  from pop group by 1,2 order by 3 desc;

-- 5. distribuicao de `touches` e de `violations` das linhas que dispararam
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
select touches, violations, count(*) as n,
       round(avg(r_net),4) as r_liq_medio, round(sum(r_net),2) as r_liq_soma
  from pop group by 1,2 order by 1,2;

-- 6. geometria vista pela decisao: linhas, pivos, linhas aposentadas por barra
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
select round(avg(lines),3) as linhas_media, min(lines) as linhas_min, max(lines) as linhas_max,
       round(avg(pivots),3) as pivos_media, min(pivots) as pivos_min, max(pivots) as pivos_max,
       round(avg(retired),4) as aposentadas_media, max(retired) as aposentadas_max,
       count(*) filter (where retired > 0) as decisoes_com_aposentada,
       count(*) filter (where canal_atr is not null) as com_canal,
       round(avg(canal_atr),4) as canal_atr_medio,
       round(avg(dist_atr),4) as dist_evento_atr_media,
       round(avg(rvol),4) as rvol_medio,
       count(distinct line_id) as linhas_distintas
  from pop;

commit;
