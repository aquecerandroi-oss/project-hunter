begin transaction isolation level repeatable read read only;
select r.run_id, s.key as strategy_key, sv.version, r.window_from, r.window_to,
       array_length(r.markets,1) as n_markets, r.started_at, r.finished_at,
       (r.finished_at - r.started_at) as duration, r.workers, r.bars_evaluated, r.errors
from replay_runs r
join strategy_versions sv on sv.id = r.strategy_version_id
join strategies s on s.id = sv.strategy_id
order by r.started_at desc
limit 30;
commit;
