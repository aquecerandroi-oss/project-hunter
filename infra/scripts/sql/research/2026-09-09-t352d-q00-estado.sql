-- T3.52d q00 — estado antes de qualquer escrita: migração aplicada, catálogo vivo,
-- os dois pais (mean_reversion v6, momentum v8) e a série horária de regime.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

-- 1. a migração
select version_num as alembic_version from alembic_version;

-- 2. catálogo vivo (ativas), com política e contexto exigido
select s.key, sv.version, sv.status::text, sv.purpose,
       sv.eligibility_policy,
       sv.activated_at, sv.deprecated_at,
       left(sv.code_ref, 28) as code_ref
  from strategy_versions sv
  join strategies s on s.id = sv.strategy_id
 where sv.status = 'active'
 order by s.key, sv.version;

-- 3. os dois pais
select s.key, sv.id, sv.version, sv.status::text, sv.purpose,
       sv.default_parameters, sv.eligibility_policy, sv.code_ref
  from strategy_versions sv
  join strategies s on s.id = sv.strategy_id
 where (s.key = 'mean_reversion' and sv.version = 'v6')
    or (s.key = 'momentum' and sv.version = 'v8')
 order by s.key;

-- 4. a série horária: existe? quantas horas, quais rótulos, quão fresca
select scope::text, classifier_version, count(*) as horas,
       min(start_time) as primeira, max(start_time) as ultima
  from market_regimes
 group by 1,2 order by 1,2;

select regime::text as rotulo, count(*) as horas
  from market_regimes
 where scope = 'btc' and classifier_version = 'regime_hourly_v1'
 group by 1 order by 2 desc;

-- 5. distribuição de rótulo na janela de replay (31 d)
select regime::text as rotulo, count(*) as horas,
       round(100.0 * count(*) / sum(count(*)) over (), 2) as pct
  from market_regimes
 where scope = 'btc' and classifier_version = 'regime_hourly_v1'
   and start_time >= timestamptz '2026-08-08 00:00:00+00'
   and start_time <  timestamptz '2026-09-08 00:00:00+00'
 group by 1 order by 2 desc;

commit;
