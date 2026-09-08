begin transaction isolation level repeatable read read only;
\pset border 2
select now() as read_at;
select level, component, event, left(message,105) as mensagem, created_at
  from system_events
 where created_at >= timestamptz '2026-09-08 18:50:00+00'
   and (component = 'activate_strategy_version'
        or (component='replay_engine' and (message like '%momentum v5%' or message like '%momentum v6%')))
 order by created_at;
select (select count(*) from shadow_outbox o join agent_signals a on a.id=o.signal_id
          join strategy_versions sv on sv.id=a.strategy_version_id
         where sv.version in ('v5','v6')
           and sv.strategy_id=(select id from strategies where key='momentum')) as outbox_das_variantes,
       (select count(*) from agent_signals a join strategy_versions sv on sv.id=a.strategy_version_id
         where sv.version='v5' and sv.strategy_id=(select id from strategies where key='momentum')) as sinais_v5_total,
       (select count(*) from agent_signals a join strategy_versions sv on sv.id=a.strategy_version_id
         where sv.version='v6' and sv.strategy_id=(select id from strategies where key='momentum')) as sinais_v6_total,
       (select count(*) from agent_signals a join signal_outcomes o on o.signal_id=a.id
          join strategy_versions sv on sv.id=a.strategy_version_id
         where sv.version='v6' and sv.strategy_id=(select id from strategies where key='momentum')
           and o.meta->>'cohort' <> 'replay:9a08835a-ae13-4c23-b521-734b2f60a3a2') as sinais_v6_fora_da_coorte,
       (select count(*) from shadow_episodes e where e.cohort in
          ('replay:72cf5671-ec16-4d62-afd6-ace3f7bbf4e1','replay:9a08835a-ae13-4c23-b521-734b2f60a3a2')) as slots;
commit;
