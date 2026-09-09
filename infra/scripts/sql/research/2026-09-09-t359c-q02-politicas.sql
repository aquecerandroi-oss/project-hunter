-- T3.59c q02 — as quatro politicas congeladas na coluna (inteiros, nao strings). SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;
select s.key||' '||sv.version as versao, sv.status::text, sv.purpose,
       jsonb_typeof(sv.eligibility_policy->'hours'->'utc'->0->0) as tipo_do_limite,
       sv.eligibility_policy::text as policy,
       sv.changelog
  from strategy_versions sv join strategies s on s.id = sv.strategy_id
 where (s.key='mean_reversion' and sv.version in ('v12','v13'))
    or (s.key='momentum' and sv.version in ('v12','v13'))
 order by 1;
commit;
