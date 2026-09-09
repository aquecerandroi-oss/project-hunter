-- T3.59c/T3.57b q40 — catalogo depois, e os recibos em system_events. SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

select s.key, sv.version, sv.status::text, sv.purpose,
       coalesce(sv.eligibility_policy::text,'-') as policy,
       sv.deprecated_at
  from strategy_versions sv join strategies s on s.id = sv.strategy_id
 where sv.status = 'active' order by s.key, sv.version;

select e.created_at, e.event, e.data->>'key' as chave, e.data->>'version' as versao
  from system_events e
 where e.component = 'activate_strategy_version'
   and e.created_at > timestamptz '2026-09-09 18:20:00+00'
 order by e.created_at;
commit;
