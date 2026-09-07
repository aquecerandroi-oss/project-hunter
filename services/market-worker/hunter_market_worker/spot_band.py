"""D12 — the exit-only hysteresis band around the spot universe floor (T3.0e).

Split out of ``spot_universe.py`` for the 350-line budget (CLAUDE.md), along
the seam ``coverage_limits.py``/``heartbeat_events.py`` already established:
this module is the **policy** (what counts as an observation, how a durable
streak turns into a removal), never the refresh orchestration.

D12 in one line: **the band is exit-only, admission never relaxes.** A pair
still needs the full 50M USDT floor (``spot_universe.SPOT_VOLUME_FLOOR_USDT``)
to enter; once in, it only leaves for a volume reason after reading below 80%
of that floor for three consecutive refreshes (``PROMUSDT`` flapped in and out
between two refreshes at ~50M, ``notes-T3.0c.md`` §8/``t30-proof.md`` §2), or
immediately, with no band and no count, if it stops trading, stops being
quoted in USDT, or is blocklisted.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_core.domain.enums import MarketStatus, MarketType

if TYPE_CHECKING:
    from collections.abc import Collection

    import redis.asyncio as redis_asyncio

    from hunter_core.domain.market import NormalizedMarket, NormalizedTicker

SPOT_QUOTE = "USDT"
"""The wallet's numeraire. A BTC-quoted pair is a different instrument."""

SPOT_EXIT_FLOOR_USDT = Decimal("40000000")
"""D12: 80% of ``spot_universe.SPOT_VOLUME_FLOOR_USDT`` -- **exit only**,
never admission. A pair already in the universe leaves the band only once it
reads below this for :data:`SPOT_EXIT_STREAK` consecutive refreshes; nothing
ever *enters* below the full 50M floor."""

SPOT_EXIT_STREAK = 3
"""D12: consecutive refreshes below :data:`SPOT_EXIT_FLOOR_USDT` before an
admitted pair leaves -- about 45 minutes at the 15-minute refresh cadence.
Longer than the oscillation measured in ``PROMUSDT`` (T3.0c/notes-T3.0c.md
§8), shorter than momentum's slowest decision horizon (4h)."""

REASON_NOT_TRADING = "not_trading"
REASON_QUOTE_NOT_USDT = "quote_not_usdt"
REASON_BLOCKLISTED = "blocklisted"
REASON_BELOW_BAND = "below_band_3x"
"""D12's four exit reasons. The first three are immediate -- no band, no
count, exactly like the admission rule they mirror; only the fourth is
reached by way of the durable streak."""

_HARD_EXIT_REASONS = frozenset({REASON_NOT_TRADING, REASON_QUOTE_NOT_USDT, REASON_BLOCKLISTED})


def permanence_observation(
    market: NormalizedMarket | None,
    ticker: NormalizedTicker | None,
    *,
    exit_floor: Decimal = SPOT_EXIT_FLOOR_USDT,
    blocklist: Collection[str] = (),
) -> str:
    """Where one already-monitored spot pair stands this refresh (D12).

    Only ever called for a symbol that is *already* in the universe --
    admission is untouched and still goes through
    ``spot_universe.tradable_symbols``. Three conditions remove a pair
    immediately, with no band and no count, mirroring the admission rule's
    own hard requirements: it stopped trading (including having vanished
    from the exchange's listing entirely, which reads the same as ``market
    is None``), it stopped being quoted in USDT, or it was blocklisted.
    Short of those, only the *exit* floor matters, and an unreadable ticker
    counts as an observation **below** it -- never above, exactly like the
    admission rule's own "no ticker = not eligible".
    """
    if market is None or market.status is not MarketStatus.ACTIVE:
        return REASON_NOT_TRADING
    if market.quote != SPOT_QUOTE:
        return REASON_QUOTE_NOT_USDT
    if market.symbol.upper() in {s.upper() for s in blocklist}:
        return REASON_BLOCKLISTED
    if ticker is None or ticker.quote_volume_24h is None or ticker.quote_volume_24h < exit_floor:
        return "below"
    return "above"


def resolve_band(streak: int, observation: str) -> tuple[int, str | None]:
    """The durable streak coming in, this cycle's :func:`permanence_observation`
    going in, the streak to persist and the removal reason (if any) coming out.

    Pure and Redis-agnostic on purpose: the counter itself has to survive a
    restart of the shard 0 process, but the rule that decides what to do with
    it is tested without touching Redis at all. A hard-exit observation
    always removes regardless of the streak it interrupts (D12: "sem banda e
    sem contagem"); ``"above"`` resets a partial streak to zero -- two
    observations below the floor followed by one above cost nothing.
    """
    if observation in _HARD_EXIT_REASONS:
        return 0, observation
    if observation == "above":
        return 0, None
    streak += 1
    if streak >= SPOT_EXIT_STREAK:
        return 0, REASON_BELOW_BAND
    return streak, None


def _band_state_key(exchange: str) -> str:
    """``mkt:{exchange}:spot:band_state`` -- one Redis hash, ``{symbol:
    streak}``, alongside the venue's other ``mkt:`` state. Durable across a
    restart of the shard 0 process (the only writer, ``spot.collects_spot``)
    because it lives in Redis, a separate process; the AOF persistence the
    VPS Redis already runs (``infra/vps/docker-compose.prod.yml``) is a
    second line of defence, not what the restart guarantee depends on.
    """
    return f"mkt:{exchange}:spot:band_state"


async def _advance_band(
    redis: redis_asyncio.Redis, exchange: str, symbol: str, observation: str
) -> str | None:
    """Read the durable streak, resolve it, write the result back.

    One ``HGET`` plus one ``HSET``/``HDEL`` per already-monitored symbol per
    refresh -- fifteen-minute cadence, at most 19 symbols, one writer by
    construction (no other shard ever runs the spot loop), so there is no
    concurrent writer to race and no need for the compare-and-set Lua script
    ``universe_leader`` needs for the multi-shard perpetual snapshot.
    """
    key = _band_state_key(exchange)
    raw = await redis.hget(key, symbol)
    streak_in = int(raw) if raw is not None else 0
    streak_out, reason = resolve_band(streak_in, observation)
    if streak_out == 0:
        await redis.hdel(key, symbol)
    else:
        await redis.hset(key, symbol, str(streak_out))
    return reason


async def apply_permanence_band(
    redis: redis_asyncio.Redis,
    exchange: str,
    old_monitored: set[str],
    markets: list[NormalizedMarket],
    tickers: dict[str, NormalizedTicker],
    blocklist: Collection[str],
) -> tuple[set[str], dict[str, str]]:
    """Which of ``old_monitored`` survive this refresh, and why the rest left.

    Only touches symbols already in the universe -- a symbol not yet
    monitored has no streak to advance and enters, if it does, purely through
    ``spot_universe.tradable_symbols``'s admission floor.
    """
    market_by_symbol = {m.symbol: m for m in markets if m.market_type is MarketType.SPOT}
    survivors: set[str] = set()
    removed_reasons: dict[str, str] = {}
    for symbol in sorted(old_monitored):
        observation = permanence_observation(
            market_by_symbol.get(symbol), tickers.get(symbol), blocklist=blocklist
        )
        reason = await _advance_band(redis, exchange, symbol, observation)
        if reason is None:
            survivors.add(symbol)
        else:
            removed_reasons[symbol] = reason
    return survivors, removed_reasons
