-- T3.52d q01 — as coortes de replay já existentes dos pais (v6, v8) e o que elas cobrem.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

select r.cohort, s.key, sv.version, r.window_from, r.window_to,
       array_length(r.markets,1) as n_mkt, r.markets, r.bars_evaluated, r.signals, r.started_at, r.finished_at
  from replay_runs r
  join strategy_versions sv on sv.id = r.strategy_version_id
  join strategies s on s.id = sv.strategy_id
 where s.key in ('mean_reversion','momentum','mean_reversion_h1')
 order by r.started_at desc
 limit 40;

commit;
