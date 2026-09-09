-- T3.52d q13 — recibos e isolamento: as duas linhas novas, a politica congelada,
-- os eventos de auditoria e a prova de que nenhuma coorte de replay publicou outbox.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

select s.key, sv.version, sv.status::text, sv.purpose, sv.eligibility_policy::text,
       sv.activated_at, sv.changelog
  from strategy_versions sv join strategies s on s.id = sv.strategy_id
 where sv.version = 'v11' order by s.key;

select component, event, created_at, left(message, 90) as message
  from system_events
 where created_at >= timestamptz '2026-09-09 15:26:00+00'
   and component in ('strategy_catalog','replay_engine','activation')
 order by created_at limit 40;

select 'outbox de coorte de replay' as prova, count(*) as linhas
  from shadow_outbox o
 where o.payload->>'cohort' in (
   'replay:5bcfbda1-9365-467e-ad14-583fcfa9ae4b',
   'replay:4a60a3dc-334c-4faa-9790-c321063ff23e');

commit;
