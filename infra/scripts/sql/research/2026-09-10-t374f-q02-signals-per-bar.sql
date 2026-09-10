-- T3.74f q02: decision lag (emitted_at - observation_ts) for every signal of
-- the last 20 minutes, newest first -- the same shape T3.74e's q01 used to
-- show the spread inside one closed bar, reused here for the pre-sharding
-- burst profile at the 19:45Z/20:00Z boundaries.
begin transaction isolation level repeatable read read only;
select s.id,
       ex.code as exchange,
       m.symbol,
       m.market_type,
       (s.supporting_features->>'observation_ts')::timestamptz as observation_ts,
       s.emitted_at,
       round(extract(epoch from (s.emitted_at - (s.supporting_features->>'observation_ts')::timestamptz))::numeric, 2) as lag_s
from agent_signals s
join markets m on m.id = s.market_id
join exchanges ex on ex.id = m.exchange_id
where s.emitted_at > now() - interval '20 minutes'
  and s.supporting_features ? 'observation_ts'
order by s.emitted_at desc
limit 60;
commit;
