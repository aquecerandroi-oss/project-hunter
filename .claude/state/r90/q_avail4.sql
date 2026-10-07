BEGIN READ ONLY;
SET LOCAL statement_timeout='300s';
SELECT count(*) n, count(dispatched_at) nd, percentile_cont(0.99) WITHIN GROUP (ORDER BY extract(epoch FROM dispatched_at - created_at)) p99, max(extract(epoch FROM dispatched_at - created_at)) mx FROM outbox_events WHERE stream='market.derivatives';
SELECT split_part(payload->>'key',':',1) ex, count(*) FROM outbox_events WHERE stream='market.derivatives' GROUP BY 1;
COMMIT;
