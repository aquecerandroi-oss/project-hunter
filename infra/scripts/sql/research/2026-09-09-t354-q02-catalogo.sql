-- T3.54 q02 — o catalogo vivo antes de qualquer escrita: toda versao de
-- mean_reversion / momentum / session_orb, com status, purpose, code_ref,
-- params_hash e a geometria declarada (atr_timeframe incluso, que e a alavanca
-- desta tarefa). SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '120s';
\pset border 2
\pset numericlocale off
select now() as read_at;

select s.key||' '||sv.version as versao,
       sv.status::text as status,
       sv.purpose::text as purpose,
       sv.code_ref,
       sv.default_parameters->>'atr_timeframe' as atr_tf,
       sv.default_parameters->>'trend_timeframe' as trend_tf,
       sv.default_parameters->>'atr_pct_min' as atr_pct_min,
       sv.default_parameters->>'atr_pct_max' as atr_pct_max,
       sv.default_parameters->>'stop_atr' as stop_atr,
       sv.default_parameters->>'target_atr' as target_atr,
       sv.default_parameters->>'atr_bars' as atr_bars,
       sv.activated_at
  from strategy_versions sv
  join strategies s on s.id = sv.strategy_id
 where s.key in ('mean_reversion', 'momentum', 'session_orb')
 order by s.key, length(sv.version), sv.version;
commit;
