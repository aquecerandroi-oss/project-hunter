begin transaction isolation level repeatable read read only;
select date_trunc('hour', started_at) as hour_utc, count(*) as slices,
       sum(extract(epoch from (finished_at-started_at))) as busy_seconds,
       round(100.0*sum(extract(epoch from (finished_at-started_at)))/3600,1) as pct_of_hour
from replay_runs
where started_at >= '2026-09-08 00:00:00+00'
group by 1 order by 1;
commit;
