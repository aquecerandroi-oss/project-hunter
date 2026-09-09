-- T3.47b q00 — o catalogo ANTES de qualquer escrita: roster completo (status, purpose,
-- linhagem no changelog) e a geometria declarada da linhagem mean_reversion.
-- Somente leitura.
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;

-- 1. roster inteiro por status
select s.key || ' ' || sv.version as versao,
       sv.status, sv.purpose,
       to_char(sv.activated_at, 'YYYY-MM-DD HH24:MI:SS.US') as ativada_em,
       to_char(sv.deprecated_at, 'YYYY-MM-DD HH24:MI:SS.US') as aposentada_em,
       left(sv.changelog, 96) as changelog
  from strategy_versions sv
  join strategies s on s.id = sv.strategy_id
 order by s.key, (regexp_replace(sv.version, '\D', '', 'g'))::int;

-- 2. quantas versoes ativas (a carga do roster)
select sv.status, count(*) as versoes
  from strategy_versions sv
 group by 1 order by 1;

-- 3. geometria declarada da linhagem mean_reversion (o pai da T3.47b e as irmas)
select s.key || ' ' || sv.version as versao, sv.status,
       sv.default_parameters->>'atr_pct_min' as atr_pct_min,
       sv.default_parameters->>'atr_pct_max' as atr_pct_max,
       sv.default_parameters->>'stop_atr'    as stop_atr,
       sv.default_parameters->>'target_atr'  as target_atr,
       sv.default_parameters->>'target2_atr' as target2_atr,
       sv.default_parameters->>'horizon_s'   as horizon_s,
       sv.code_ref
  from strategy_versions sv
  join strategies s on s.id = sv.strategy_id
 where s.key = 'mean_reversion'
 order by (regexp_replace(sv.version, '\D', '', 'g'))::int;

-- 4. as tres versoes a aposentar: existe posicao/slot aberto? (o que --deprecate checaria)
select s.key || ' ' || sv.version as versao, sv.purpose, sv.status,
       (select count(*) from shadow_episodes e
         where e.strategy_version_id = sv.id and e.open_outcome_signal_id is not null) as slots_abertos,
       (select count(*) from agent_signals a where a.strategy_version_id = sv.id) as sinais,
       (select count(*) from agent_signals a
         where a.strategy_version_id = sv.id
           and a.supporting_features->>'cohort' = 'prospective') as sinais_prospectivos
  from strategy_versions sv
  join strategies s on s.id = sv.strategy_id
 where (s.key, sv.version) in (('momentum','v7'), ('mean_reversion','v4'), ('mean_reversion','v5'))
 order by s.key, sv.version;
commit;
