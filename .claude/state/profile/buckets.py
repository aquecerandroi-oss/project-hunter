import sys, collections
path = sys.argv[1]
BUCKETS = [
    ("idle/select (epoll wait)", ("selectors.py", "select (selectors", "_run_once (asyncio/base_events.py:19")),
    ("websockets deflate+frames", ("permessage_deflate", "websockets/frames.py", "websockets/protocol.py")),
    ("json.loads (stdlib)", ("json/decoder.py", "json/__init__.py")),
    ("pydantic model __init__", ("pydantic/main.py",)),
    ("normalize: Decimal/datetime", ("hunter_exchanges/binance/normalize.py",)),
    ("redis client (encode/send/parse)", ("redis/asyncio", "redis/_parsers", "redis/connection")),
    ("msgpack", ("msgpack",)),
    ("sqlalchemy", ("sqlalchemy",)),
    ("ssl read/socket", ("ssl.py", "sslproto.py", "selector_events.py")),
]
self_c = collections.Counter(); total = 0
rows = []
for line in open(path, encoding="utf-8", errors="replace"):
    line = line.rstrip("\n")
    if not line.strip(): continue
    stack, _, cnt = line.rpartition(" ")
    try: n = int(cnt)
    except ValueError: continue
    frames = stack.split(";"); total += n; rows.append((frames, n))
print(f"TOTAL SAMPLES: {total}")
print("\n== SELF TIME BY SUBSYSTEM (leaf frame) ==")
for name, keys in BUCKETS:
    s = sum(n for frames, n in rows if any(k in frames[-1] for k in keys))
    print(f"{100*s/total:6.2f}%  {name}")
print("\n== CUMULATIVE BY WORKER TASK (top-of-stack app frame) ==")
task = collections.Counter()
for frames, n in rows:
    hit = next((f for f in frames if "forever (hunter_market_worker" in f or "hunter_market_worker" in f), None)
    task[frames[1] if len(frames)>1 else frames[0]] += n
print("\n== CUMULATIVE for named app entrypoints ==")
NAMED = ["consume_once (hunter_market_worker/streaming.py", "handle_event (hunter_market_worker/ingest.py",
         "write_ticker (hunter_market_worker/hot_state.py", "push_trade (hunter_market_worker/hot_state.py",
         "write_book (hunter_market_worker/hot_state.py", "push_candle (hunter_market_worker/hot_state.py",
         "_hash (hunter_market_worker/hot_state.py", "flush_ticks (hunter_market_worker/ingest.py",
         "drain_loop", "snapshot_loop", "run_recovery", "oi_poll_loop", "run_heartbeat", "run_funding", "run_universe",
         "_handle_raw_message (hunter_exchanges", "parse_stream_message", "parse_book_ticker", "parse_depth20",
         "parse_agg_trade", "parse_kline_ws", "parse_mark_price", "publish (hunter_market_worker/publication",
         "data_received (websockets"]
for nm in NAMED:
    s = sum(n for frames, n in rows if any(nm in f for f in frames))
    if s: print(f"{100*s/total:6.2f}%  {s:6d}  {nm}")
