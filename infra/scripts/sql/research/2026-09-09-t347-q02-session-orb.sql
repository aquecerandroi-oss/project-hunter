-- T3.47 q02 — parametros completos da session_orb v1 (ela nao declara stop_atr/target_atr).
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;
select sv.version, jsonb_pretty(sv.default_parameters) as parametros
  from strategy_versions sv join strategies s on s.id=sv.strategy_id
 where s.key='session_orb' and sv.status='active';
commit;
