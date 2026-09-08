-- T3.42 q00 — o pai congelado antes de qualquer escrita.
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;
select s.key, sv.version, sv.status, sv.purpose, sv.code_ref, sv.params_format,
       sv.created_at, sv.activated_at
  from strategy_versions sv join strategies s on s.id=sv.strategy_id
 where s.key = 'mean_reversion' order by sv.version;
select sv.version, jsonb_pretty(sv.default_parameters) as parametros
  from strategy_versions sv join strategies s on s.id=sv.strategy_id
 where s.key = 'mean_reversion' order by sv.version;
commit;
