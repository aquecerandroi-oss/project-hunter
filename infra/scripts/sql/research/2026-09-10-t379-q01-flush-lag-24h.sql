-- T3.79 q01: candle close (open_time + 1m) -> DB commit (candles.received_at),
-- last 24h, only the 1m timeframe (the one the strategy-worker consumes).
-- This is the DB-committed proxy for the "flush" hop; the live in-process
-- observation (hunter_market_worker.latency, close_time -> post-flush
-- utcnow()) is a few ms tighter since it runs before the outbox dispatch, not
-- after the whole INSERT round-trips back to this reader.
--
-- source = 'ws' only: a REST-backfilled minute (source = 'rest', 30203 of
-- 343k rows in this window) has received_at = whenever the backfill job ran,
-- not a real flush latency -- included it would inflate this hop's p95 into
-- the tens of thousands of seconds, which is a backfill artifact, not the
-- live pipeline being slow (found while running this exact query, see
-- notes-T3.79.md).
begin transaction isolation level repeatable read read only;
select date_trunc('hour', open_time) as hour_utc,
       count(*) as candles,
       round(percentile_cont(0.5) within group (
         order by extract(epoch from (received_at - (open_time + interval '1 minute')))
       )::numeric, 3) as mediana_s,
       round(percentile_cont(0.95) within group (
         order by extract(epoch from (received_at - (open_time + interval '1 minute')))
       )::numeric, 3) as p95_s,
       round(min(extract(epoch from (received_at - (open_time + interval '1 minute'))))::numeric, 3)
         as min_s
from candles
where timeframe = '1m'
  and open_time >= now() - interval '24 hours'
  and is_final
  and source = 'ws'
group by 1
order by 1;
commit;
