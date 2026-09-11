"""Which markets one strategy-worker shard evaluates (T3.74f).

**Why sharding, measured.** T3.74e raised ``worker_concurrency`` from 8 to 32
to drain a ~200-market burst inside one process (projected ~10s). Live on the
VPS the projection did not hold: ``docker stats`` during the 2026-09-10
19:45Z boundary showed ``hunter-strategy-worker-1`` pinned at 97-99.5% of one
core for the whole ~36s the burst took to drain, while ``hunter-postgres-1``
stayed at 20-25% of its 12 cores the same window (notes-T3.74f.md §1) — one
``asyncio`` process cannot spend more than one core's worth of CPU no matter
how many coroutines are "concurrent" (the GIL), so raising concurrency past
the point where the burst's *aggregate* work is CPU-bound stops buying
throughput; it only adds scheduling overhead (measured: per-stage means grew
under the higher concurrency, not shrank). Splitting the ~200-market universe
across ``N`` processes is the lever that actually adds CPU, because each
shard is its own OS process with its own core.

**The mapping.** Every shard uses ``hunter_core.sharding.owns`` — the exact
formula ``hunter_market_worker.universe.shard_symbols`` already uses for
``MARKET_SHARD`` — so a symbol's shard index is the same number in both
services even though nothing here imports the market-worker package. Sharded
by the plain symbol (``BTCUSDT``, not ``exchange:symbol:market_type``): the
Shadow Lab only ever decides on the perpetual listing (``consumer.py``'s
``DECISION_MARKET_TYPE`` refusal already narrows the venue), and there is
exactly one exchange (``binance``) today, so ``market_key``'s extra fields in
``dispatch.py`` would not change which shard a bar lands on, only add a
constant string to hash.

**Consumer topology (documented, not just chosen).** Each shard reads the
*whole* ``market.candles.closed`` stream through its **own** consumer group
(:func:`hunter_strategy_worker.config.consumer_group`, e.g.
``strategy-worker.shadow.1of4``) — the same shape
``hunter_market_worker.backfill.BackfillConsumer`` already uses for "shared
stream, sharded ownership" (its own ``group`` property embeds
``{shard_index}of{shard_total}``, and ``BackfillConsumer.owns`` refuses a
request for a symbol it does not own). A **single shared** group across
shards cannot do this correctly: ``XREADGROUP`` hands each new stream entry
to whichever competing consumer calls it next, not to the shard whose crc32
slice contains the symbol — a shared group would silently drop bars handed
to the "wrong" shard instead of guaranteeing exactly one evaluation per bar.
Per-shard groups cost each non-owning shard one cheap read-and-ack per bar it
does not own (no query, no ``handle_candle`` call — refused in
``consumer.py::run_consumer`` before the dispatcher ever sees it, counted as
``hunter_shadow_bars_skipped_total{reason="not_my_shard"}``), which is
negligible next to the CPU this module exists to spread out.

Per-market ordering is unaffected: a market is owned by exactly one shard, so
every bar of that market is only ever evaluated by that shard's own
:class:`~hunter_strategy_worker.dispatch.BarDispatcher`, which already
serialises per market (T3.74c). No double processing: a bar is evaluated by
its owning shard's group and acked-without-evaluating by every other shard's
group — one evaluation, ``N`` acks, one per group, exactly what a consumer
group is for.
"""

from __future__ import annotations

from hunter_core.sharding import owns
from hunter_strategy_worker.config import CONSUMER_GROUP, HEARTBEAT_KEY

__all__ = [
    "consumer_group",
    "consumer_groups",
    "heartbeat_key",
    "heartbeat_keys",
    "owns_market",
]


def owns_market(symbol: str, shard_index: int, shard_total: int) -> bool:
    """Whether this shard evaluates ``symbol``. ``shard_total <= 1`` (the
    default, unsharded deployment) owns every symbol -- ``owns()`` already
    returns that (``x % 1 == 0`` always), spelled out here so a reader does
    not have to work out the degenerate case from the general formula."""
    return shard_total <= 1 or owns(symbol, shard_index, shard_total)


def consumer_group(shard_index: int, shard_total: int) -> str:
    """This shard's own consumer group on ``market.candles.closed``.

    Each shard reads the **whole** stream through its own group instead of
    sharing one across shards -- module docstring above has the full
    reasoning (the same shape
    ``hunter_market_worker.backfill.BackfillConsumer.group`` already uses for
    "shared stream, sharded ownership"). ``shard_total <= 1`` returns
    :data:`~hunter_strategy_worker.config.CONSUMER_GROUP` unchanged, byte for
    byte -- a solo deployment never has to migrate a consumer group's
    pending entries.
    """
    if shard_total <= 1:
        return CONSUMER_GROUP
    return f"{CONSUMER_GROUP}.{shard_index}of{shard_total}"


def heartbeat_key(shard_index: int, shard_total: int) -> str:
    """This shard's own heartbeat hash, mirroring
    :func:`hunter_market_worker.heartbeat.hb_key`'s ``{i}of{N}`` suffix
    convention so the API's generic ``/system/workers`` scan
    (``hunter_api.services.system_status.parse_heartbeat_key``, which splits
    on the first ``:`` and treats the rest as the instance label) shows one
    row per shard for free, with no change to that scan. ``shard_total <= 1``
    returns :data:`~hunter_strategy_worker.config.HEARTBEAT_KEY` unchanged.
    """
    if shard_total <= 1:
        return HEARTBEAT_KEY
    return f"{HEARTBEAT_KEY}:{shard_index}of{shard_total}"


def consumer_groups(shard_total: int) -> tuple[str, ...]:
    """Every shard's own consumer group for a topology of ``shard_total``
    processes (T3.87) -- ``tuple(consumer_group(i, shard_total) for i in
    range(shard_total))``, spelled out here so the replay gate's readiness
    check (``hunter_strategy_worker.replay.budget``) derives the whole set
    from the *same* function every shard already uses, never a second
    formula that could drift from it (the bug this closes: the gate held its
    own hard-coded ``"strategy-worker.shadow"`` literal, which stopped being
    any live shard's group the moment ``STRATEGY_SHARDS > 1`` shipped,
    T3.74f)."""
    total = max(1, shard_total)
    return tuple(consumer_group(i, total) for i in range(total))


def heartbeat_keys(shard_total: int) -> tuple[str, ...]:
    """Every shard's own heartbeat key for a topology of ``shard_total``
    processes (T3.87) -- the heartbeat-side twin of :func:`consumer_groups`,
    same reasoning."""
    total = max(1, shard_total)
    return tuple(heartbeat_key(i, total) for i in range(total))
