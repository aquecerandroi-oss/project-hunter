-- T3.81 q01: flush-lag distribution by minute-of-hour (source='ws' only, last 6h)
-- flush lag proxy = candles.received_at - (open_time + 1 minute) = close_time
-- Minute-of-hour groups the 60 possible bar-close instants to see whether the
-- lag pattern is uniform (batch-timer floor) or spikes at specific offsets
-- (e.g. universe refresh at :00/:15/:30/:45, T2.5g's 15-min cadence).
SELECT
    EXTRACT(MINUTE FROM open_time)::int AS minute_of_hour,
    count(*) AS candles,
    round(percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (received_at - (open_time + interval '1 minute'))))::numeric, 3) AS p50_s,
    round(percentile_cont(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (received_at - (open_time + interval '1 minute'))))::numeric, 3) AS p95_s,
    round(min(EXTRACT(EPOCH FROM (received_at - (open_time + interval '1 minute'))))::numeric, 3) AS min_s,
    round(max(EXTRACT(EPOCH FROM (received_at - (open_time + interval '1 minute'))))::numeric, 3) AS max_s
FROM candles
WHERE source = 'ws'
  AND open_time >= now() - interval '6 hours'
  AND timeframe = '1m'
GROUP BY 1
ORDER BY 1;
