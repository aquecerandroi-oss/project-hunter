-- T3.42 q18 — roster: ordenacao real do worker (paper antes, versao numerica) sobre as ativas.
begin transaction isolation level repeatable read read only;
\pset border 2
select now() as read_at;
select row_number() over (order by s.key,
                          case when sv.purpose='paper' then 0 else 1 end,
                          coalesce(nullif(regexp_replace(sv.version,'^v',''),'')::int, 999999),
                          sv.version) as pos,
       s.key, sv.version, sv.purpose,
       substring(sv.changelog from 'params_hash=([0-9a-f]+)') as params_hash
  from strategy_versions sv join strategies s on s.id=sv.strategy_id
 where sv.status='active';
commit;
