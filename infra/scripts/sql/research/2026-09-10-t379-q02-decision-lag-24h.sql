-- T3.79 q02: candle close -> agent_signals.emitted_at, last 24h -- the same
-- computation T3.74c's q01 used, rerun for T3.79's own reporting window
-- (T3.74c/T3.74d's dispatcher fix had not reached the VPS as of that task's
-- own notes; whether it has by the time this runs is exactly what this
-- query, and notes-T3.79.md's own timestamp, answer).
begin transaction isolation level repeatable read read only;
select date_trunc('hour', emitted_at) as hour_utc,
       count(*) as sinais,
       round(percentile_cont(0.5) within group (
         order by extract(epoch from (emitted_at - (supporting_features->>'observation_ts')::timestamptz))
       )::numeric, 1) as mediana_s,
       round(percentile_cont(0.95) within group (
         order by extract(epoch from (emitted_at - (supporting_features->>'observation_ts')::timestamptz))
       )::numeric, 1) as p95_s,
       round(max(extract(epoch from (emitted_at - (supporting_features->>'observation_ts')::timestamptz)))::numeric, 1) as max_s
from agent_signals
where emitted_at >= now() - interval '24 hours'
  and supporting_features ? 'observation_ts'
group by 1 order by 1;
commit;
