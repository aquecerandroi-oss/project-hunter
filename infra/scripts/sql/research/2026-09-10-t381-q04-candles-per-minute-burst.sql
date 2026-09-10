-- T3.81 q04: how many final ws candles arrive per real second within one
-- close-minute burst (last 30 min) -- shows how wide the arrival window is
-- vs. persist.py's FLUSH_INTERVAL_S=1.0 forced wait.
SELECT
    date_trunc('minute', open_time) AS bar_minute,
    date_trunc('second', received_at) AS received_second,
    count(*) AS candles
FROM candles
WHERE source = 'ws'
  AND timeframe = '1m'
  AND open_time >= now() - interval '30 minutes'
GROUP BY 1, 2
ORDER BY 1 DESC, 2
LIMIT 200;
