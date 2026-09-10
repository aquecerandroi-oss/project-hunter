-- T3.81 q03: how much of the flush lag is the batch-write itself vs the
-- outbox publish step. outbox_events.created_at (queued inside the same
-- transaction as the candle row, so ~= candles.received_at for that minute)
-- to dispatched_at (when the XADD actually landed) for market.candles.closed,
-- last 6h.
SELECT
    date_trunc('minute', created_at) AS minute,
    count(*) AS events,
    round(percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (dispatched_at - created_at)))::numeric, 3) AS p50_s,
    round(percentile_cont(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (dispatched_at - created_at)))::numeric, 3) AS p95_s,
    round(max(EXTRACT(EPOCH FROM (dispatched_at - created_at)))::numeric, 3) AS max_s,
    count(*) FILTER (WHERE dispatched_at IS NULL) AS still_pending
FROM outbox_events
WHERE stream = 'market.candles.closed'
  AND created_at >= now() - interval '6 hours'
GROUP BY 1
ORDER BY 1 DESC
LIMIT 60;
