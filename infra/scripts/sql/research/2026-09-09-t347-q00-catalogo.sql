-- T3.47 q00 — catalogo das versoes vivas e os parametros de geometria dos pais
-- citados no brief (mean_reversion v2/v3, momentum v6, session_orb v1). Somente leitura.
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at, current_database() as db;

-- 1. roster: tudo que esta ativo agora, na ordem que o worker usa (roster.py:110-129)
select row_number() over (order by s.key,
                          case when sv.purpose='paper' then 0 else 1 end,
                          coalesce(nullif(regexp_replace(sv.version,'^v',''),'')::int, 999999),
                          sv.version) as pos,
       s.key, sv.version, sv.status, sv.purpose,
       substring(sv.changelog from 'params_hash=([0-9a-f]+)') as params_hash,
       sv.activated_at
  from strategy_versions sv join strategies s on s.id = sv.strategy_id
 where sv.status = 'active';

-- 2. geometria declarada dos pais do brief
select s.key||' '||sv.version as versao,
       sv.default_parameters->>'atr_pct_min' as atr_pct_min,
       sv.default_parameters->>'atr_pct_max' as atr_pct_max,
       sv.default_parameters->>'stop_atr' as stop_atr,
       sv.default_parameters->>'target_atr' as target_atr,
       sv.default_parameters->>'target2_atr' as target2_atr,
       sv.default_parameters->>'target3_atr' as target3_atr,
       sv.default_parameters->>'horizon_s' as horizon_s,
       sv.default_parameters->>'max_entry_delay_s' as entry_delay_s
  from strategy_versions sv join strategies s on s.id = sv.strategy_id
 where (s.key, sv.version) in (('mean_reversion','v1'),('mean_reversion','v2'),('mean_reversion','v3'),
                               ('momentum','v2'),('momentum','v6'),('session_orb','v1'))
 order by 1;

-- 3. code_ref completo dos pais que vou derivar
select s.key||' '||sv.version as versao, sv.code_ref
  from strategy_versions sv join strategies s on s.id = sv.strategy_id
 where (s.key, sv.version) in (('mean_reversion','v2'),('mean_reversion','v3'),('momentum','v6'))
 order by 1;
commit;
