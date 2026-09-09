-- T3.66 q00 — catálogo da família mean_reversion: versões, parâmetros congelados e
-- CONTAGEM de desfechos por versão/coorte. SOMENTE LEITURA.
--
-- Isto é DESENHO, não resultado: nenhuma coluna aqui é um R, um retorno ou uma
-- expectancy. O que se lê é quantas decisões existem (poder) e qual a geometria
-- congelada de cada versão (o que o controle pareado precisa copiar).
begin transaction isolation level repeatable read read only;

select now() as read_at;

select sv.id, s.key as familia, sv.version, sv.purpose, sv.status,
       sv.default_parameters->>'stop_atr'      as stop_atr,
       sv.default_parameters->>'target_atr'    as target_atr,
       sv.default_parameters->>'horizon_s'     as horizon_s,
       sv.default_parameters->>'atr_pct_min'   as atr_pct_min,
       sv.default_parameters->>'atr_pct_max'   as atr_pct_max,
       sv.default_parameters->>'assumed_spread_bps' as spread_bps,
       sv.default_parameters->>'slippage_bps'  as slippage_bps,
       sv.default_parameters->>'fee_bps'       as fee_bps,
       sv.default_parameters->>'max_entry_delay_s' as max_delay_s,
       sv.eligibility_policy::text     as porta
  from strategy_versions sv
  join strategies s on s.id = sv.strategy_id
 where s.key = 'mean_reversion'
 order by sv.version;

select s.key || ' ' || sv.version as versao,
       case when coalesce(a.supporting_features->>'cohort', o.meta->>'cohort','') like 'replay:%'
            then 'replay' else 'prospective' end as coorte,
       o.tracking_state::text as estado,
       count(*) as n,
       count(*) filter (where o.r_multiple is not null) as com_r,
       min((o.meta->'entry_plan'->>'source_bar_close')::timestamptz) as primeira_barra,
       max((o.meta->'entry_plan'->>'source_bar_close')::timestamptz) as ultima_barra,
       count(distinct a.market_id) as mercados
  from signal_outcomes o
  join agent_signals a      on a.id  = o.signal_id
  join strategy_versions sv on sv.id = a.strategy_version_id
  join strategies s         on s.id  = sv.strategy_id
 where s.key = 'mean_reversion'
   and a.emitted_at < timestamptz '2026-09-09 02:30:00+00'
 group by 1,2,3
 order by 1,2,3;

commit;
