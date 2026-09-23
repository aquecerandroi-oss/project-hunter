copy (
  select m.symbol, extract(epoch from c.open_time)::bigint/60, c.close::float8, c.high::float8,
         c.low::float8, c.volume::float8, coalesce(c.trade_count,-1),
         coalesce(c.taker_buy_volume,-1)::float8
  from candles c join markets m on m.id = c.market_id
  join spot_desk_markets s on s.binance_symbol = m.symbol and s.enabled
  where c.timeframe = '1m' and c.is_final and m.market_type = 'perpetual'
    and m.symbol not in ('ETHUSDT','LINKUSDT','ZECUSDT','BNBUSDT','DOGEUSDT','UNIUSDT',
                         'ARBUSDT','TAOUSDT')
  order by m.symbol, c.open_time
) to stdout with (format csv);
