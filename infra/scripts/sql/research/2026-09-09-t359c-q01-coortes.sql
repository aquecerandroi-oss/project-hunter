-- T3.59c/T3.57b q01 — coortes de replay existentes por versao. SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

select s.key, sv.version, sv.status::text,
       a.supporting_features->>'cohort' as cohort,
       count(*) as sinais,
       min(a.emitted_at) as primeiro, max(a.emitted_at) as ultimo
  from agent_signals a
  join strategy_versions sv on sv.id = a.strategy_version_id
  join strategies s on s.id = sv.strategy_id
 where s.key in ('mean_reversion','momentum','trendline_breakout')
   and a.supporting_features->>'cohort' like 'replay:%'
 group by 1,2,3,4 order by 1,2,4;

-- versoes trendline_breakout
select s.key, sv.version, sv.status::text, sv.purpose, sv.code_ref,
       sv.activated_at, sv.deprecated_at
  from strategy_versions sv join strategies s on s.id = sv.strategy_id
 where s.key = 'trendline_breakout' order by sv.version;

commit;
