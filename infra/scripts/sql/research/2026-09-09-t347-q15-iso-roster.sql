-- T3.47 q15 — isolamento das seis coortes, sinais prospectivos das seis versoes novas,
-- conteudo proprio + linhagem, roster final e cobertura.
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;

select (select count(*) from shadow_outbox
          where payload->>'cohort' in ('replay:293d98b7-90e1-4dfe-a604-60556f3b175e','replay:ee11d60b-3a4e-48be-94a3-1aecb8cf16fd',
                'replay:af24ee08-01cf-41ba-9b7a-1b43172bea28','replay:66fa85cb-1d51-4330-a00b-00964b430ab4',
                'replay:9d99748b-21b9-44a7-8980-32c37b931e6e','replay:264b227f-5bc0-4930-8c5b-2e883c0a858e')
             or payload->'signal'->>'cohort' in ('replay:293d98b7-90e1-4dfe-a604-60556f3b175e','replay:ee11d60b-3a4e-48be-94a3-1aecb8cf16fd',
                'replay:af24ee08-01cf-41ba-9b7a-1b43172bea28','replay:66fa85cb-1d51-4330-a00b-00964b430ab4',
                'replay:9d99748b-21b9-44a7-8980-32c37b931e6e','replay:264b227f-5bc0-4930-8c5b-2e883c0a858e')) as outbox_das_coortes,
       (select count(*) from shadow_outbox where dispatched_at is null) as outbox_pendente_total;

select s.key||' '||sv.version as versao,
       coalesce(a.supporting_features->>'cohort','(sem)') as coorte,
       count(*) as sinais, min(a.emitted_at) as primeiro
  from agent_signals a join strategy_versions sv on sv.id=a.strategy_version_id
  join strategies s on s.id=sv.strategy_id
 where (s.key,sv.version) in (('momentum','v7'),('momentum','v8'),('mean_reversion','v4'),
                              ('mean_reversion','v5'),('mean_reversion','v6'),('mean_reversion','v7'))
 group by 1,2 order by 1,2;

select s.key||' '||sv.version as versao, sv.status, sv.purpose,
       sv.default_parameters->>'atr_pct_min' as atr_pct_min,
       sv.default_parameters->>'stop_atr' as stop_atr,
       sv.default_parameters->>'target_atr' as target_atr,
       sv.default_parameters->>'target2_atr' as target2_atr,
       sv.default_parameters->>'target3_atr' as target3_atr,
       (sv.code_ref = (select p.code_ref from strategy_versions p where p.strategy_id=sv.strategy_id and p.version='v1')) as code_ref_igual_ao_v1,
       left(sv.changelog, 120) as changelog
  from strategy_versions sv join strategies s on s.id=sv.strategy_id
 where (s.key,sv.version) in (('momentum','v6'),('momentum','v7'),('momentum','v8'),
                              ('mean_reversion','v2'),('mean_reversion','v3'),('mean_reversion','v4'),
                              ('mean_reversion','v5'),('mean_reversion','v6'),('mean_reversion','v7'))
 order by 1;

select row_number() over (order by s.key,
                          case when sv.purpose='paper' then 0 else 1 end,
                          coalesce(nullif(regexp_replace(sv.version,'^v',''),'')::int, 999999),
                          sv.version) as pos,
       s.key, sv.version, sv.purpose,
       substring(sv.changelog from 'params_hash=([0-9a-f]+)') as params_hash
  from strategy_versions sv join strategies s on s.id=sv.strategy_id
 where sv.status='active';
commit;
