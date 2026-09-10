-- T3.74c q02: replay_runs de hoje (10/09) -- para dizer se um lote (T3.76)
-- estava correndo durante a medicao de atraso, e por quanto tempo.
begin transaction isolation level repeatable read read only;
select r.run_id, s.key as strategy_key, sv.version, r.window_from, r.window_to,
       array_length(r.markets, 1) as n_markets, r.started_at, r.finished_at,
       (r.finished_at - r.started_at) as duration, r.workers, r.bars_evaluated, r.errors
from replay_runs r
join strategy_versions sv on sv.id = r.strategy_version_id
join strategies s on s.id = sv.strategy_id
where r.started_at >= '2026-09-10 00:00:00+00'
order by r.started_at;
commit;
