-- T3.81 q02: flush-lag distribution by estimated shard and by market count
-- per minute, last 6h, source='ws' only, perpetual only (join markets).
--
-- CAVEAT: Postgres has no native crc32(), so ``shard_estimate`` below is a
-- stand-in (md5-derived hash % 4), NOT byte-identical to the code's
-- ``zlib.crc32(symbol) % shard_total`` (hunter_market_worker.universe.
-- shard_symbols, PIPELINE.md §1 item 8) -- it groups markets into 4 buckets
-- of similar size, useful only to sanity-check "is any bucket an outlier",
-- not to reproduce which container owns which symbol. The real per-shard
-- table in notes-T3.81.md §1 was built by computing the exact
-- zlib.crc32(symbol) % 4 in Python from the live `markets` list and running
-- one query per shard with an explicit `market_id IN (...)` -- this file is
-- kept as the honest, reproducible-without-Python approximation.
SELECT
    (('x' || substr(md5(m.symbol), 1, 8))::bit(32)::bigint % 4) AS shard_estimate,
    count(*) AS candles,
    round((count(*) / (extract(epoch from (max(c.open_time) - min(c.open_time))) / 60.0 + 1))::numeric, 1) AS avg_markets_per_minute,
    round(percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (c.received_at - (c.open_time + interval '1 minute'))))::numeric, 3) AS p50_s,
    round(percentile_cont(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (c.received_at - (c.open_time + interval '1 minute'))))::numeric, 3) AS p95_s
FROM candles c
JOIN markets m ON m.id = c.market_id
WHERE c.source = 'ws'
  AND c.open_time >= now() - interval '6 hours'
  AND c.timeframe = '1m'::candle_timeframe
  AND m.market_type = 'perpetual'
GROUP BY 1
ORDER BY 1;
