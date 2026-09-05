**Jitter is resolved; #3 and #6 are not fully resolved.** Two new must-fix issues were reproduced.

- **Jitter:** `23.5h × (1 − rand() × 0.1)` never exceeds 23.5h.
- **#3:** Mid-handshake additions now receive catch-up commands, but catch-up introduces the failures below.
- **#6:** ACK-only failures correctly stop after three attempts with backoffs `[1, 2]`. However, [streams.py:339](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/streams.py:339) skips bookTicker validation when no trade price is cached. An empty bookTicker payload therefore returns “healthy”; five successive frame-then-disconnect cycles all retained one-second backoffs. Validate deferred bookTicker frames before resetting attempts.

**New must-fix issues:**

1. **[P1] Catch-up can unsubscribe a currently desired symbol.** [subscriptions.py:202](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/subscriptions.py:202) computes differences before awaiting sends, without coordinating with `update()`. Reproduced: open with BTC+OLD; handshake changes membership to BTC+ETH; while catch-up’s SUBSCRIBE ETH awaits, re-add OLD. Commands become `SUBSCRIBE ETH → SUBSCRIBE OLD → UNSUBSCRIBE OLD`. Desired membership includes OLD, but the socket omits it until reconnect. Serialize catch-up and live updates per connection.

2. **[P2] Catch-up send failures bypass reconnect handling.** [ws.py:241](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/ws.py:241) awaits catch-up outside the receive/retry exception handler. Reproduced a disconnect during catch-up SUBSCRIBE: the consumer received raw `ConnectionResetError` after **one connection attempt, zero backoffs**, terminating the merged stream. Include catch-up in the reconnect error boundary.

Validation: **153 unit tests passed**, plus in-memory failure probes. No files modified.