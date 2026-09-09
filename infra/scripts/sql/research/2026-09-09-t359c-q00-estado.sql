-- T3.59c/T3.57b q00 — estado antes de qualquer escrita.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

-- 1. migração
select version_num as alembic_version from alembic_version;

-- 2. catálogo vivo
select s.key, sv.version, sv.status::text, sv.purpose,
       sv.eligibility_policy::text as policy,
       sv.activated_at, left(sv.code_ref, 34) as code_ref
  from strategy_versions sv
  join strategies s on s.id = sv.strategy_id
 where sv.status in ('active','draft')
 order by s.key, sv.version;

-- 3. os pais da EXP-0023
select s.key, sv.version, sv.status::text, sv.purpose,
       sv.eligibility_policy::text as policy, sv.params_format,
       md5(sv.default_parameters::text) as params_md5, sv.code_ref
  from strategy_versions sv
  join strategies s on s.id = sv.strategy_id
 where (s.key = 'mean_reversion' and sv.version in ('v10','v11'))
    or (s.key = 'momentum' and sv.version in ('v10','v11'))
 order by s.key, sv.version;

-- 4. familia trendline_bounce ja existe?
select key, name, description from strategies order by key;

-- 5. coortes de replay existentes por versao
select s.key, sv.version, sig.cohort, count(*) as sinais,
       min(sig.emitted_at) as primeiro, max(sig.emitted_at) as ultimo
  from agent_signals sig
  join strategy_versions sv on sv.id = sig.strategy_version_id
  join strategies s on s.id = sv.strategy_id
 where s.key in ('mean_reversion','momentum','trendline_breakout')
 group by 1,2,3 order by 1,2,3;

-- 6. serie horaria de regime
select scope::text, classifier_version, count(*) as horas,
       min(start_time) as primeira, max(start_time) as ultima
  from market_regimes group by 1,2 order by 1,2;

commit;
