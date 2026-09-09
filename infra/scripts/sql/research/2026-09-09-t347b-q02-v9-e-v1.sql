-- T3.47b q02 — a recusa do D2: "piso 0,006 e nada mais" reconstroi a mean_reversion v1.
-- Prova pelos parametros congelados e pelo recibo do replay ja existente da v1.
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;

-- 1. os parametros congelados de v1 e v2 lado a lado (o D2 pedia v2 com atr_pct_min=0.006)
select s.key||' '||sv.version as versao, sv.status, sv.purpose,
       sv.default_parameters->>'atr_pct_min' as atr_pct_min,
       sv.default_parameters->>'atr_pct_max' as atr_pct_max,
       sv.default_parameters->>'stop_atr'    as stop_atr,
       sv.default_parameters->>'target_atr'  as target_atr,
       sv.default_parameters->>'target2_atr' as target2_atr,
       sv.default_parameters->>'horizon_s'   as horizon_s,
       sv.default_parameters->>'entry_delay_s' as entry_delay_s,
       sv.default_parameters->>'max_entry_delay_s' as max_entry_delay_s
  from strategy_versions sv join strategies s on s.id = sv.strategy_id
 where s.key='mean_reversion' and sv.version in ('v1','v2')
 order by sv.version;

-- 2. o recibo do replay ja existente da v1 (mesma janela? mesmos mercados? mesmo lag?)
select left(r.cohort,24) as coorte, s.key||' '||sv.version as versao,
       to_char(r.window_from,'YYYY-MM-DD') as de, to_char(r.window_to,'YYYY-MM-DD') as ate,
       array_length(r.markets,1) as mkts, array_to_string(r.markets,',') as mercados,
       r.bars_evaluated as bars, r.signals as sig, r.outcomes_resolved as out,
       r.outcomes_open as aberto, r.decision_lag_s as lag, r.workers as wk, r.errors as err,
       to_char(r.started_at,'YYYY-MM-DD HH24:MI:SS') as inicio
  from replay_runs r
  join strategy_versions sv on sv.id = r.strategy_version_id
  join strategies s on s.id = sv.strategy_id
 where s.key='mean_reversion' and sv.version in ('v1','v2')
 order by r.started_at;
commit;
