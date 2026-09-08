begin transaction isolation level repeatable read read only;
\pset border 2
select sv.version, sv.changelog
  from strategy_versions sv join strategies s on s.id=sv.strategy_id
 where s.key='mean_reversion' order by sv.version;
commit;
