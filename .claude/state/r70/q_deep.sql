SET statement_timeout='1800s';
COPY (
  SELECT m.symbol, (extract(epoch from c.open_time)::bigint/60), c.close::float8, c.high::float8,
         c.low::float8, c.volume::float8, coalesce(c.trade_count,-1),
         coalesce(c.taker_buy_volume,-1)::float8
  FROM candles c JOIN markets m ON m.id = c.market_id
  WHERE c.timeframe = '1m' AND c.is_final AND m.market_type = 'perpetual'
    AND c.open_time >= TIMESTAMPTZ '2026-07-25 00:00+00'
    AND m.symbol IN ('BTCUSDT','ETHUSDT','XRPUSDT','LINKUSDT','DASHUSDT','ZECUSDT','BNBUSDT',
                     'DOGEUSDT','SOLUSDT','UNIUSDT','NEARUSDT','ARBUSDT','SUIUSDT','TAOUSDT',
                     'PROMUSDT','SAHARAUSDT')
  ORDER BY m.symbol, c.open_time
) TO STDOUT WITH (FORMAT csv);
