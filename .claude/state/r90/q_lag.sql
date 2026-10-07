-- R90 / H-033 — calibração CEGA da folga: quanto depois do bucket a leitura de OI existe (instante real e inserção).
BEGIN READ ONLY;
SET LOCAL statement_timeout='600s';
WITH e AS (
  SELECT (payload->'payload'->>'bucket_ts')::timestamptz b,
         (payload->'payload'->>'ts')::timestamptz rt,
         created_at c
  FROM outbox_events
  WHERE stream = 'market.derivatives' AND payload->'payload'->>'bucket_ts' IS NOT NULL
)
SELECT (b AT TIME ZONE 'UTC')::date d, count(*) n,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM c - b)) c_p50,
       percentile_cont(0.99) WITHIN GROUP (ORDER BY extract(epoch FROM c - b)) c_p99,
       max(extract(epoch FROM c - b)) c_max,
       max(extract(epoch FROM rt - b)) rt_max,
       min(extract(epoch FROM rt - b)) rt_min,
       sum((c - b > interval '5 minutes')::int) c_gt5m
FROM e GROUP BY 1 ORDER BY 1;
COMMIT;
