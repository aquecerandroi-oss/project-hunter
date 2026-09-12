"""``POST https://swap-api.pump.fun/v1/coins/market-activity/batch`` — the
activity of **many** coins per request, per window (``docs/PUMPFUN.md`` §2
route 4; T4.2g). Pure: the model and the parser; the request is
``SwapApiClient.market_activity_batch`` (``swap_api.py``).

**Measured live on 12/09/2026, 20:24–20:25 UTC, five requests paced 4 s apart
(``tests/fixtures/pumpfun/t42g_market_activity_batch_probes.json``):**

- the body is ``{addresses[], intervals[], metrics[]}`` and the answer is
  ``201`` with ``{mint: {interval: {metric: number} | null}}``;
- **at most 50 addresses per request** — 140 and 100 are refused with a
  ``400`` whose validator says ``addresses must contain no more than 50
  elements``; an empty list says ``at least 1 elements``. :data:`MAX_ADDRESSES`
  is that number and the client refuses to exceed it before spending budget;
- every one of the ten metrics is accepted, the six the screener's own call
  does not ask for included (``numBuys``, ``numSells``, ``buyVolumeUSD``,
  ``sellVolumeUSD``, ``numBuyers``, ``numSellers``);
- the intervals ``1m``, ``5m``, ``1h``, ``6h``, ``24h`` are all accepted by
  the validator and echoed as keys. **A window with no trade is ``null``**,
  not an object of zeros: on 50 seven-hour-old coins ``24h`` was an object
  for 50, ``6h`` for 7 and ``1h``/``5m``/``1m`` for none — a ``null`` under a
  window the same response filled for another coin is a stated zero.
  **Unproven here:** a non-null ``1m`` block on a coin trading *now* (the
  fifth probe was spent on an empty list — a bug of the probe, not of the
  API); the worker therefore treats a window as *live* only when the response
  filled it for at least one coin (:attr:`ActivityBatch.windows_live`) and
  publishes that in the heartbeat instead of assuming;
- volumes are **USD** as JSON floats (``buyVolumeUSD: 49.60028645179046``),
  decoded with ``parse_float=Decimal`` and kept as USD here: this package does
  not own a SOL/USD quote, and a SOL figure without the quote it came from is
  a number nobody can check (``NormalizedSolPrice``'s own rule);
- 50 coins cost one request of the **same Cloudflare budget** as the trade
  tape (~20/60 s per IP, ``swap_api.py``): 982 ms and 17 KB; two coins 243 ms;
- the response carries no timestamp of its own: ``observed_at`` is the
  server's ``Date`` header (second precision) — the instant the windows end —
  and ``received_at`` is ours.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from typing import Any, Literal, cast

from hunter_core.domain.types import ensure_utc, utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.pumpfun.models import ReceivedAtMixin

logger = get_logger(__name__)

EXCHANGE = "pumpfun_swap_api"
ACTIVITY_SOURCE = "swap_api:market-activity/batch"
MAX_ADDRESSES = 50
"""The validator's ceiling, measured: ``addresses must contain no more than 50 elements``."""
WINDOW_SECONDS: dict[str, int] = {"1m": 60, "5m": 300, "1h": 3600, "6h": 21600, "24h": 86400}
"""Every interval the validator accepted, and what it means in seconds."""
DEFAULT_WINDOWS: tuple[str, ...] = ("1m", "5m")
METRICS: tuple[str, ...] = (
    "numTxs",
    "volumeUSD",
    "numUsers",
    "numBuys",
    "numSells",
    "buyVolumeUSD",
    "sellVolumeUSD",
    "numBuyers",
    "numSellers",
    "priceChangePercent",
)


class NormalizedMarketActivity(ReceivedAtMixin):
    """One coin over one window, as the batch route counted it.

    ``observed_at`` is the response's ``Date`` — the instant the window ends
    (``(observed_at − window_s, observed_at]``); ``received_at`` is ours.
    Volumes are USD, as delivered. ``unique_buyers`` counts every buyer, the
    creator included — the route does not say who traded, so a consumer that
    excluded the creator from the tape's count cannot do it here.
    """

    kind: Literal["meme_market_activity"] = "meme_market_activity"
    mint: str
    window: str
    window_s: int
    num_txs: int
    buys: int
    sells: int
    unique_users: int
    unique_buyers: int
    unique_sellers: int
    volume_usd: Decimal
    buy_volume_usd: Decimal
    sell_volume_usd: Decimal
    price_change_pct: Decimal | None
    """``priceChangePercent`` as the route says it (a percent, signed)."""
    source: str = ACTIVITY_SOURCE


@dataclass(frozen=True, slots=True)
class ActivityBatch:
    """One request: every reading, every stated-empty window per coin, which
    windows the response filled for anyone, and what it could not parse."""

    readings: tuple[NormalizedMarketActivity, ...]
    empty: dict[str, tuple[str, ...]] = field(default_factory=dict[str, tuple[str, ...]])
    """Window → mints whose block was ``null`` (no trade in the window)."""
    windows_live: frozenset[str] = frozenset()
    """Windows the response filled for at least one coin: a ``null`` under one
    of these is a stated zero; a ``null`` under a window nobody filled is not
    proven to mean anything and the caller must not write a zero from it."""
    missing: tuple[str, ...] = ()
    """Mints asked for that the response did not name."""
    malformed: int = 0
    asked: int = 0
    observed_at: datetime = field(default_factory=utcnow)
    received_at: datetime = field(default_factory=utcnow)


def _malformed(text: str) -> MalformedMessage:
    return MalformedMessage(f"swap-api market-activity {text}", exchange=EXCHANGE)


def _count(value: Any, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _malformed(f"{key} is not a non-negative integer: {value!r}")
    return value


def _money(value: Any, key: str) -> Decimal:
    """USD as a JSON number decoded to ``Decimal``; a ``float`` (a body decoded
    without ``parse_float=Decimal``) is refused rather than rounded."""
    if isinstance(value, bool) or not isinstance(value, (int, Decimal, str)):
        raise _malformed(f"{key} is not a decimal: {value!r}")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise _malformed(f"{key} is not decimal: {value!r}") from exc
    if not result.is_finite() or result < 0:
        raise _malformed(f"{key} is negative or not finite: {value!r}")
    return result


def parse_activity_block(
    mint: str,
    window: str,
    raw: dict[str, Any],
    *,
    observed_at: datetime,
    received_at: datetime,
) -> NormalizedMarketActivity:
    if window not in WINDOW_SECONDS:
        raise _malformed(f"unknown window {window!r}")
    change = raw.get("priceChangePercent")
    change_pct: Decimal | None = None
    if change is not None:
        if isinstance(change, bool) or not isinstance(change, (int, Decimal, str)):
            raise _malformed(f"priceChangePercent is not a decimal: {change!r}")
        try:
            change_pct = Decimal(change)
        except InvalidOperation as exc:
            raise _malformed("priceChangePercent is not decimal") from exc
        if not change_pct.is_finite():
            raise _malformed("priceChangePercent is not finite")
    return NormalizedMarketActivity(
        mint=mint,
        window=window,
        window_s=WINDOW_SECONDS[window],
        num_txs=_count(raw.get("numTxs"), "numTxs"),
        buys=_count(raw.get("numBuys"), "numBuys"),
        sells=_count(raw.get("numSells"), "numSells"),
        unique_users=_count(raw.get("numUsers"), "numUsers"),
        unique_buyers=_count(raw.get("numBuyers"), "numBuyers"),
        unique_sellers=_count(raw.get("numSellers"), "numSellers"),
        volume_usd=_money(raw.get("volumeUSD"), "volumeUSD"),
        buy_volume_usd=_money(raw.get("buyVolumeUSD"), "buyVolumeUSD"),
        sell_volume_usd=_money(raw.get("sellVolumeUSD"), "sellVolumeUSD"),
        price_change_pct=change_pct,
        observed_at=observed_at,
        received_at=received_at,
    )


def parse_activity_batch(
    raw: Any,
    *,
    mints: Sequence[str],
    windows: Sequence[str],
    observed_at: datetime,
    received_at: datetime,
) -> ActivityBatch:
    """A whole response. A block the parser refuses is counted and skipped so
    one strange coin does not lose the other forty-nine; a body that is not an
    object is malformed as a whole. Only the mints and windows *asked for* are
    read — anything else the server adds is not a claim this parser makes."""
    if not isinstance(raw, dict):
        raise _malformed("response is not an object")
    payload = cast(dict[str, Any], raw)
    readings: list[NormalizedMarketActivity] = []
    empty: dict[str, list[str]] = {window: [] for window in windows}
    live: set[str] = set()
    missing: list[str] = []
    malformed = 0
    for mint in mints:
        block = payload.get(mint)
        if block is None:
            missing.append(mint)
            continue
        if not isinstance(block, dict):
            malformed += 1
            logger.warning("swap_api_malformed_activity", mint=mint, error="block is not an object")
            continue
        coin = cast(dict[str, Any], block)
        for window in windows:
            metrics = coin.get(window)
            if metrics is None:
                empty[window].append(mint)
                continue
            if not isinstance(metrics, dict):
                malformed += 1
                continue
            try:
                readings.append(
                    parse_activity_block(
                        mint,
                        window,
                        cast(dict[str, Any], metrics),
                        observed_at=observed_at,
                        received_at=received_at,
                    )
                )
                live.add(window)
            except MalformedMessage as exc:
                malformed += 1
                logger.warning("swap_api_malformed_activity", mint=mint, error=str(exc))
    return ActivityBatch(
        readings=tuple(readings),
        empty={window: tuple(mints_) for window, mints_ in empty.items()},
        windows_live=frozenset(live),
        missing=tuple(missing),
        malformed=malformed,
        asked=len(mints),
        observed_at=observed_at,
        received_at=received_at,
    )


def response_stamp(headers: dict[str, str], *, received_at: datetime) -> datetime:
    """The server's ``Date`` as UTC — the instant the windows end. Absent or
    unreadable, the receive time (and the caller may say so)."""
    value = headers.get("date")
    if not value:
        return received_at
    try:
        return ensure_utc(parsedate_to_datetime(value))
    except (TypeError, ValueError):
        return received_at


__all__ = [
    "ACTIVITY_SOURCE",
    "DEFAULT_WINDOWS",
    "MAX_ADDRESSES",
    "METRICS",
    "WINDOW_SECONDS",
    "ActivityBatch",
    "NormalizedMarketActivity",
    "parse_activity_batch",
    "parse_activity_block",
    "response_stamp",
]
