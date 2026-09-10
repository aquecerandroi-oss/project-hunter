begin transaction isolation level repeatable read read only;
select date_trunc('hour', emitted_at) as hour_utc,
       count(*) as sinais,
       round(percentile_cont(0.5) within group (
         order by extract(epoch from (emitted_at - (supporting_features->>'observation_ts')::timestamptz))
       )::numeric, 1) as mediana_s,
       round(percentile_cont(0.95) within group (
         order by extract(epoch from (emitted_at - (supporting_features->>'observation_ts')::timestamptz))
       )::numeric, 1) as p95_s
from agent_signals
where emitted_at >= '2026-09-08 00:00:00+00'
  and supporting_features ? 'observation_ts'
group by 1 order by 1;
commit;
