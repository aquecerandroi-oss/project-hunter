-- T3.62 q00 — catalogo vivo da familia mean_reversion antes de qualquer replay:
-- versao, estado, proposito, parametros que importam (atr_pct_min, stop_atr,
-- alvos, atr_timeframe/atr_bars), politica de elegibilidade e linhagem.
-- Serve para provar que v6, v10, v8 e v2 estao ativas e quais sao os parametros
-- que o replay vai usar. SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '120s';
\pset border 2
\pset numericlocale off
select now() as read_at;

select sv.version,
       sv.status::text as estado,
       sv.purpose::text as proposito,
       sv.default_parameters->>'atr_pct_min'   as atr_pct_min,
       sv.default_parameters->>'stop_atr'      as stop_atr,
       sv.default_parameters->>'target_atr'    as alvo1,
       sv.default_parameters->>'target2_atr'   as alvo2,
       sv.default_parameters->>'atr_timeframe' as atr_tf,
       sv.default_parameters->>'atr_bars'      as atr_bars,
       coalesce(sv.eligibility_policy::text, '-') as politica,
       right(sv.code_ref, 16) as code_ref_sufixo, left(sv.changelog, 60) as changelog,
       sv.activated_at
  from strategy_versions sv
  join strategies s on s.id = sv.strategy_id
 where s.key = 'mean_reversion'
 order by (regexp_replace(sv.version, '\D', '', 'g'))::int;
commit;
