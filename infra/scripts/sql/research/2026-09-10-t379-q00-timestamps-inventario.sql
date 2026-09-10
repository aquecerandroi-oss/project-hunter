-- T3.79 q00: which timestamp already exists per hop, and how many rows in
-- the last 24h each one is computed from. Read-only inventory, not a p50/p95.
begin transaction isolation level repeatable read read only;

-- hop "ingest" (exchange event -> market-worker receive): NormalizedTrade.ts/
-- NormalizedCandle.event_ts and .received_at are Pydantic fields on the
-- in-memory wire model (packages/core/hunter_core/domain/market.py) -- never
-- persisted to Postgres (only a *final* candle's OHLCV is). There is no SQL
-- column this hop can be measured from; it did not exist before this task's
-- own Prometheus histogram + heartbeat fields (hunter_market_worker.latency).
select 'ingest: no persisted timestamp -- see module docstring above' as gap;

-- hop "flush" (candle close -> durably queued): candles.received_at already
-- exists (server_default now()) -- how many final 1m candles in the window.
select count(*) as candles_1m_24h,
       min(open_time) as first_open_time,
       max(open_time) as last_open_time
from candles
where timeframe = '1m' and open_time >= now() - interval '24 hours';

-- hop "decision" (candle close -> agent_signals.emitted_at): T3.74c already
-- reads this off supporting_features->>'observation_ts'.
select count(*) as agent_signals_24h
from agent_signals
where emitted_at >= now() - interval '24 hours'
  and supporting_features ? 'observation_ts';

-- hop "admission" (agent_signals.emitted_at -> trade_proposals.decided_at):
-- the join exists (trade_proposals.signal_id -> agent_signals.id); whether
-- there are any rows to join is a separate question, answered below.
select count(*) as trade_proposals_total,
       count(*) filter (where signal_id is not null) as with_signal_id,
       count(*) filter (where decided_at is not null) as decided
from trade_proposals;

-- hop "fill" (trade_proposals.decided_at -> a fill's own ts): orders.filled_at
-- would be the natural column; whether there is any row at all is below.
select count(*) as orders_total, count(*) filter (where completed_at is not null) as completed
from orders;
select count(*) as fills_total from fills;

commit;
