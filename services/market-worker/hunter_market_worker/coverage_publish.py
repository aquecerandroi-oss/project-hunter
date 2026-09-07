"""Publishing ``mkt:{exchange}:coverage`` when there is more than one collector.

The scanner reads **one** hash per exchange (``session_since``,
``covered_until``, ``sym:{symbol}`` — ``services/scanner-worker/
hunter_scanner_worker/coverage.py``), and that reader is not this task's to
change. With ``MARKET_SHARD=i/N`` there are now N processes writing it, so a
plain ``HSET`` of the two scalars is last-writer-wins: a healthy shard would
publish a fresh ``covered_until`` that the scanner then applies to the symbols
of a **stuck** shard — precisely the fabricated coverage
``hunter_market_worker.coverage`` exists to prevent (Astra, T2.5g review,
must-fix 4).

So every stamp is one Lua script (atomic, no read-modify-write race between
shards) over two keys:

- ``mkt:{exchange}:coverage`` — the reader's contract, unchanged;
- ``mkt:{exchange}:coverage:shards`` — one record per shard:
  ``{i}of{N}:since``, ``{i}of{N}:until`` (both ``epoch|iso``), ``{i}of{N}:ts``
  (when it last stamped) and ``{i}of{N}:syms`` (the symbols it currently
  claims, so its own fields can be reconciled by *any* stamp, including after
  it restarts with a smaller universe and has no memory of what it published).

The aggregate the reader sees:

- ``covered_until = MIN`` over live shard records. The most-behind collector
  bounds the whole exchange — conservative, never optimistic. Freezing one
  shard costs evaluation lag for every market, never a false claim;
- ``session_since = MIN`` over live shard records, which is only a *lower*
  bound: the honest per-market answer is the ``sym:{symbol}`` value itself,
  which each shard declares as ``max(its own session, that symbol's own
  subscription)`` and the script publishes as the **latest** value any live
  claimant declares. The reader takes ``max(sym, session_since)``, so a shard
  that just restarted penalizes exactly its own markets, and while a topology
  change has two shards claiming the same symbol the old owner's older start
  can never overwrite the new owner's (Astra, T2.5g diff review);
- a shard whose record is older than :data:`SHARD_RECORD_TTL_S` is dropped by
  whoever stamps next, and every stamp re-establishes the invariant that the
  published ``sym:`` fields are **exactly the union of the live records' own
  lists**. A dead shard's markets go back to ``insufficient_coverage`` (nobody
  is collecting them) instead of inheriting a sibling's proof, a symbol whose
  owner changed keeps the field its new owner publishes, and no field can
  survive with no owner at all — which is what happened in the first live run
  (an 8 → 4 topology change left ``KOMAUSDT`` behind, claimed by no process and
  deletable by none, i.e. coverage claimed for a market nobody collects);
- no live record at all ⇒ both scalars written empty, which the reader already
  understands as "the collector is here and cannot prove continuity", distinct
  from a missing key ("no collector").

``N == 1`` runs the same script (one record, ``MIN`` of one), which also fixes
a solo bug this rewrite inherited: symbols dropped from the universe across a
**restart** used to stay in the hash forever, because reconciliation depended
on a per-process set that a new process starts empty.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from redis.exceptions import NoScriptError

from hunter_core.domain.enums import MarketType
from hunter_core.redis import keys

if TYPE_CHECKING:
    from collections.abc import Mapping

    import redis.asyncio as redis_asyncio

SHARD_RECORD_TTL_S = 15.0
"""How stale a shard's record may be before another shard drops it (and its
symbols) from the aggregate. Deliberately the scanner's own
``MAX_PROOF_AGE_S``: past it the proof would be refused anyway, so keeping the
record alive only risks the *other* shards' claims looking older than they are.
Well above the 0.25s stamp cadence — a loaded collector may skip a few."""

SESSION_SINCE = "session_since"
COVERED_UNTIL = "covered_until"
SYMBOL_PREFIX = "sym:"

_SCRIPT = """
local cov, shards = KEYS[1], KEYS[2]
local id = ARGV[1]
local now = tonumber(ARGV[2])
local record_ttl = tonumber(ARGV[3])
local key_ttl = tonumber(ARGV[4])
local since, until_ = ARGV[5], ARGV[6]
local payload = ARGV[7]

redis.call('HSET', shards,
    id .. ':since', since,
    id .. ':until', until_,
    id .. ':ts', ARGV[2],
    id .. ':syms', payload)

-- every shard's record, live and stale
local raw = redis.call('HGETALL', shards)
local records = {}
for i = 1, #raw, 2 do
    local rid, part = string.match(raw[i], '^(.+):([^:]+)$')
    if rid then
        records[rid] = records[rid] or {}
        records[rid][part] = raw[i + 1]
    end
end

local claimed = {}
local stale = {}
local min_since, min_until = nil, nil
for rid, rec in pairs(records) do
    local ts = tonumber(rec['ts'] or '')
    if ts == nil or (now - ts) > record_ttl then
        stale[#stale + 1] = rid
    else
        -- A symbol's start is the LATEST any live claimant declares: during a
        -- topology change two shards own it for a few seconds, and the old
        -- owner's older start would let the reader accept a window crossing
        -- the handover (Astra, T2.5g diff review).
        for line in string.gmatch(rec['syms'] or '', '([^\\n]+)') do
            local name, epoch, iso = string.match(line, '^([^\\t]+)\\t([^\\t]+)\\t(.*)$')
            if name and tonumber(epoch) then
                local current = claimed[name]
                if current == nil or tonumber(epoch) > current[1] then
                    claimed[name] = {tonumber(epoch), iso}
                end
            end
        end
        local se, si = string.match(rec['since'] or '', '^([^|]+)|(.*)$')
        local ue, ui = string.match(rec['until'] or '', '^([^|]+)|(.*)$')
        if se and ue and tonumber(se) and tonumber(ue) then
            if min_since == nil or tonumber(se) < min_since[1] then
                min_since = {tonumber(se), si}
            end
            if min_until == nil or tonumber(ue) < min_until[1] then
                min_until = {tonumber(ue), ui}
            end
        end
    end
end

for _, rid in ipairs(stale) do
    redis.call('HDEL', shards, rid .. ':since', rid .. ':until', rid .. ':ts', rid .. ':syms')
end

-- Full reconciliation: the published ``sym:`` fields are exactly the live
-- records' claims, values included. Publishing only this shard's own symbols
-- and deleting only what a *stale* record listed left two holes in production:
-- an orphan nobody could delete (an 8 -> 4 change left KOMAUSDT behind) and an
-- old owner overwriting the new owner's later start during a handover.
local writes = {}
for name, value in pairs(claimed) do
    writes[#writes + 1] = 'sym:' .. name
    writes[#writes + 1] = value[2]
end
if #writes > 0 then redis.call('HSET', cov, unpack(writes)) end
local orphans = {}
for _, field in ipairs(redis.call('HKEYS', cov)) do
    local name = string.match(field, '^sym:(.+)$')
    if name and not claimed[name] then orphans[#orphans + 1] = field end
end
if #orphans > 0 then redis.call('HDEL', cov, unpack(orphans)) end

if min_since ~= nil and min_until ~= nil then
    redis.call('HSET', cov, 'session_since', min_since[2], 'covered_until', min_until[2])
else
    redis.call('HSET', cov, 'session_since', '', 'covered_until', '')
end
redis.call('EXPIRE', cov, key_ttl)
redis.call('EXPIRE', shards, key_ttl)
return 1
"""

_SCRIPT_SHA_ATTR = "_hunter_coverage_publish_sha"


def shards_key(exchange: str, market_type: MarketType = MarketType.PERPETUAL) -> str:
    return f"{keys.tape_coverage(exchange, market_type)}:shards"


def shard_id(shard_index: int, shard_total: int) -> str:
    return f"{shard_index}of{shard_total}"


def _stamp_value(moment: datetime | None) -> str:
    """``epoch|iso``: the number the script compares with, next to the exact
    string the scanner parses. Comparing ISO text would work only by accident
    of formatting; comparing epochs and *publishing* the ISO keeps both honest."""
    if moment is None:
        return ""
    return f"{moment.timestamp()}|{moment.isoformat()}"


async def ensure_script_sha(redis: Any) -> str:
    sha = getattr(redis, _SCRIPT_SHA_ATTR, None)
    if sha is None:
        sha = await redis.script_load(_SCRIPT)
        setattr(redis, _SCRIPT_SHA_ATTR, sha)
    return sha


async def publish(
    redis: redis_asyncio.Redis,
    exchange: str,
    *,
    shard: str,
    session_since: datetime | None,
    covered_until: datetime | None,
    symbols: Mapping[str, datetime],
    now: datetime,
    key_ttl_s: int,
    market_type: MarketType = MarketType.PERPETUAL,
) -> None:
    """One atomic stamp: this shard's record, its symbols, and the aggregate.

    ``session_since=None`` (with no symbols) is how a shard says its interval
    ended: its record goes empty, its symbols are withdrawn, and the aggregate
    is recomputed from whoever is left — the exchange's scalars only go blank
    when *no* shard can prove anything.
    """
    payload = "\n".join(
        f"{symbol}\t{since.timestamp()}\t{since.isoformat()}" for symbol, since in symbols.items()
    )
    argv = [
        shard,
        str(now.timestamp()),
        str(SHARD_RECORD_TTL_S),
        str(key_ttl_s),
        _stamp_value(session_since),
        _stamp_value(covered_until),
        payload,
    ]
    client: Any = redis
    sha = await ensure_script_sha(client)
    # One aggregate per venue *and* market type (T3.0b): the ``sym:*`` fields
    # inside the hash are plain symbols, so a shared hash would make one
    # collector's coverage stand as proof for a market it never subscribed to.
    cov, shards = keys.tape_coverage(exchange, market_type), shards_key(exchange, market_type)
    try:
        await client.evalsha(sha, 2, cov, shards, *argv)
    except NoScriptError:
        # A Redis restart flushes the script cache (same fallback as
        # ``hot_state``): run it once by body and re-cache the SHA.
        await client.eval(_SCRIPT, 2, cov, shards, *argv)
        setattr(client, _SCRIPT_SHA_ATTR, await client.script_load(_SCRIPT))


__all__ = [
    "COVERED_UNTIL",
    "SESSION_SINCE",
    "SHARD_RECORD_TTL_S",
    "SYMBOL_PREFIX",
    "publish",
    "shard_id",
    "shards_key",
]
