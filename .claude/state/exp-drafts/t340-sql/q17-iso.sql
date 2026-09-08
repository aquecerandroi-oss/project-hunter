begin transaction isolation level repeatable read read only;
\pset border 2
select now() as read_at;
select (select count(*) from shadow_outbox o
         where o.payload->>'cohort' in ('replay:72cf5671-ec16-4d62-afd6-ace3f7bbf4e1',
                                        'replay:9a08835a-ae13-4c23-b521-734b2f60a3a2')) as outbox_das_coortes,
       (select count(*) from agent_signals a join strategy_versions sv on sv.id=a.strategy_version_id
         where sv.version='v5' and sv.strategy_id=(select id from strategies where key='momentum')) as sinais_v5_total,
       (select count(*) from agent_signals a join strategy_versions sv on sv.id=a.strategy_version_id
         where sv.version='v6' and sv.strategy_id=(select id from strategies where key='momentum')) as sinais_v6_total,
       (select count(*) from agent_signals a join signal_outcomes o on o.signal_id=a.id
          join strategy_versions sv on sv.id=a.strategy_version_id
         where sv.version='v6' and sv.strategy_id=(select id from strategies where key='momentum')
           and o.meta->>'cohort' <> 'replay:9a08835a-ae13-4c23-b521-734b2f60a3a2') as sinais_v6_fora_da_coorte,
       (select count(*) from shadow_episodes e where e.cohort in
          ('replay:72cf5671-ec16-4d62-afd6-ace3f7bbf4e1','replay:9a08835a-ae13-4c23-b521-734b2f60a3a2')) as slots,
       (select count(*) from signal_outcomes o where o.meta->>'cohort'='replay:9a08835a-ae13-4c23-b521-734b2f60a3a2'
          and o.tracking_state <> 'terminal') as v6_nao_terminais;
commit;
