"""The Lua the rate limiter runs. Every one of these is atomic by definition.

Split out of ``rate_limit.py`` so the scripts can be read (and diffed) as the
protocol they are, and so the module that runs them stays inside the 350-line
budget.

Two clocks live here on purpose. The **bucket** scripts take ``now`` from the
caller: their state is a delta (``elapsed`` since the last refill), the caller
already owns a ``clock`` injection point that tests drive, and backwards skew
is clamped to zero. The **IP gate** scripts take Redis's own ``TIME`` instead,
because ``blocked_until`` is an absolute deadline that several processes
compare against: with per-process wall clocks, a shard running a second fast
would lift a ban another shard is still serving (Astra, T2.9 round 1).
"""

from __future__ import annotations

# Refill-then-consume, atomically. Returns the wait (seconds, as a string —
# Redis Lua has no float return type) before ``weight`` tokens are available;
# "0" means the weight was consumed. Tokens are only deducted when the wait is
# zero, so a caller that ends up waiting (or raising) never loses budget it did
# not actually spend.
ACQUIRE_SCRIPT = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_per_s = tonumber(ARGV[2])
local weight = tonumber(ARGV[3])
local now = tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])  -- EXPIRE needs an int; matches RECORD_USED_WEIGHT_SCRIPT

local tokens = tonumber(redis.call('HGET', key, 'tokens'))
local ts = tonumber(redis.call('HGET', key, 'ts'))
if tokens == nil or ts == nil then
    tokens = capacity
    ts = now
end
local elapsed = now - ts
if elapsed < 0 then elapsed = 0 end
tokens = math.min(capacity, tokens + elapsed * refill_per_s)

local wait = 0
if tokens < weight then
    wait = (weight - tokens) / refill_per_s
    redis.call('HSET', key, 'tokens', tokens, 'ts', now)
else
    tokens = tokens - weight
    redis.call('HSET', key, 'tokens', tokens, 'ts', now)
end
redis.call('EXPIRE', key, ttl)
return tostring(wait)
"""

# The exchange's own accounting (``X-MBX-USED-WEIGHT-1M``) may only ever *take
# budget away*, never give it back (F3): refill first (so a header arriving
# after a long idle gap does not look artificially low), then take the minimum
# of "tokens after refill" — which already reflects every reservation this or
# another process made — and ``capacity - used_weight``.
#
# T2.9 adds the staleness guard here, where it is atomic. It used to be a
# per-process dict, so two processes racing on one key could reorder: a slower
# response carrying an older, *lower* ``used_weight`` overwrote a fresher,
# higher one and resurrected budget the exchange had already spent. ``uw`` /
# ``uw_at`` keep the highest reading of the current window next to the tokens
# it produced, so the rejection is decided once, for every process. A lower
# reading is trusted again after a full window, because the exchange's own
# counter legitimately resets then.
RECORD_USED_WEIGHT_SCRIPT = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_per_s = tonumber(ARGV[2])
local used_weight = tonumber(ARGV[3])
local now = tonumber(ARGV[4])
local window = tonumber(ARGV[5])
local ttl = tonumber(ARGV[6])  -- always last: a float TTL is rejected by EXPIRE
                               -- and the unit fake pins that by position

local last_uw = tonumber(redis.call('HGET', key, 'uw'))
local last_at = tonumber(redis.call('HGET', key, 'uw_at'))
if last_uw ~= nil and last_at ~= nil then
    if used_weight < last_uw and (now - last_at) < window then
        return 'stale'
    end
end

local tokens = tonumber(redis.call('HGET', key, 'tokens'))
local ts = tonumber(redis.call('HGET', key, 'ts'))
if tokens == nil or ts == nil then
    tokens = capacity
    ts = now
end
local elapsed = now - ts
if elapsed < 0 then elapsed = 0 end
tokens = math.min(capacity, tokens + elapsed * refill_per_s)

local proposed = capacity - used_weight
if proposed < 0 then proposed = 0 end
local new_tokens = tokens
if proposed < tokens then new_tokens = proposed end

redis.call('HSET', key, 'tokens', new_tokens, 'ts', now, 'uw', used_weight, 'uw_at', now)
redis.call('EXPIRE', key, ttl)
return tostring(new_tokens)
"""

# Extend-only: a 429 on any bucket of this IP pushes the shared deadline out,
# and a shorter Retry-After arriving later can never pull it back in. Returns
# the seconds still to wait, measured on Redis's clock so every process reads
# the same remaining time.
BLOCK_IP_SCRIPT = """
local key = KEYS[1]
local seconds = tonumber(ARGV[1])
local ttl_slack = tonumber(ARGV[2])

local time = redis.call('TIME')
local now = tonumber(time[1]) + tonumber(time[2]) / 1000000
local deadline = now + seconds
local current = tonumber(redis.call('GET', key))
if current ~= nil and current > deadline then
    deadline = current
end
redis.call('SET', key, deadline)
redis.call('EXPIRE', key, math.ceil(deadline - now) + ttl_slack)
return tostring(deadline - now)
"""

IP_WAIT_SCRIPT = """
local key = KEYS[1]
local deadline = tonumber(redis.call('GET', key))
if deadline == nil then return '0' end
local time = redis.call('TIME')
local now = tonumber(time[1]) + tonumber(time[2]) / 1000000
local remaining = deadline - now
if remaining < 0 then remaining = 0 end
return tostring(remaining)
"""

__all__ = [
    "ACQUIRE_SCRIPT",
    "BLOCK_IP_SCRIPT",
    "IP_WAIT_SCRIPT",
    "RECORD_USED_WEIGHT_SCRIPT",
]
