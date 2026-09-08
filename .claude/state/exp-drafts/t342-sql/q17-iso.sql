-- T3.42 q17 — isolamento: coorte de replay nao publica, prospectivos existem.
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;
select (select count(*) from shadow_outbox
          where payload->>'cohort' in ('replay:d570b19a-f6e2-4312-86ed-9394b16ac81a',
                                       'replay:f4af4ffe-da8b-47e4-9ad2-6af83aca59e4')
             or payload->'signal'->>'cohort' in ('replay:d570b19a-f6e2-4312-86ed-9394b16ac81a',
                                                 'replay:f4af4ffe-da8b-47e4-9ad2-6af83aca59e4')) as outbox_das_coortes,
       (select count(*) from agent_signals a join strategy_versions sv on sv.id=a.strategy_version_id
          join strategies s on s.id=sv.strategy_id where s.key='mean_reversion' and sv.version='v2') as sinais_v2_total,
       (select count(*) from agent_signals a join strategy_versions sv on sv.id=a.strategy_version_id
          join strategies s on s.id=sv.strategy_id where s.key='mean_reversion' and sv.version='v3') as sinais_v3_total,
       (select count(*) from shadow_outbox where dispatched_at is null) as outbox_pendente_total;
select s.key||' '||sv.version as versao,
       coalesce(a.supporting_features->>'cohort','(sem)') as coorte,
       count(*) as sinais, min(a.emitted_at) as primeiro
  from agent_signals a join strategy_versions sv on sv.id=a.strategy_version_id
  join strategies s on s.id=sv.strategy_id
 where s.key='mean_reversion' and sv.version in ('v2','v3')
 group by 1,2 order by 1,2;
select row_number() over (order by s.key,
                          case when sv.purpose='paper' then 0 else 1 end,
                          coalesce(nullif(regexp_replace(sv.version,'^v',''),'')::int, 999999),
                          sv.version) as pos,
       s.key, sv.version, sv.purpose, sv.params_hash
  from strategy_versions sv join strategies s on s.id=sv.strategy_id
 where sv.status='active';
commit;
