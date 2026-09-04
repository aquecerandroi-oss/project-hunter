"""Which realtime channels a principal may subscribe to (ARCHITECTURE.md §5.2).

Channel names are ``rt:market:{exchange}:{symbol}``, ``rt:radar``,
``rt:system``, and ``rt:org:{org_id}:...``. The first three carry market data
and platform notices — global, identical for everyone. The last carries one
tenant's portfolios and risk events, so it is authorized against the
principal's memberships, by parsing the organization id out of the name.

Two rules make that safe:

- the name is matched against an exact grammar, not a prefix test. ``rt:org``
  is only a tenant channel when the segment after it parses as a UUID the
  caller is an active member of.
- no wildcard is accepted from a client, ever. A subscription to
  ``rt:org:*:risk`` would be authorized against nothing, and Redis pattern
  matching would then deliver every tenant's risk events down this socket.
"""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hunter_api.auth.principal import Principal

RADAR_CHANNEL = "rt:radar"
SYSTEM_CHANNEL = "rt:system"
MARKET_PREFIX = "rt:market:"
ORG_PREFIX = "rt:org:"

MAX_CHANNEL_LENGTH = 200
MAX_CHANNELS_PER_CONNECTION = 50

_PUBLIC_EXACT = frozenset({RADAR_CHANNEL, SYSTEM_CHANNEL})
_MARKET_RE = re.compile(r"\Art:market:[a-z0-9_-]{1,32}:[A-Za-z0-9._-]{1,32}\Z")
_ORG_RE = re.compile(r"\Art:org:([0-9a-f-]{36}):[a-z0-9:_-]{1,64}\Z")
"""``\\A``/``\\Z``, never ``^``/``$``: ``$`` also matches *before* a trailing
newline, so ``rt:market:binance:BTC\\n`` would pass the grammar and then be
sent to Redis with the newline still in it — validating one name and
subscribing to another. Lower-case hex only, for the same class of reason:
``uuid.UUID`` accepts either case, so an upper-case spelling would authorize
against the right organization and subscribe to a channel name no publisher
ever writes."""

_WILDCARD_CHARS = frozenset("*?[]")

PRICE_CLASS = "prices"
RADAR_CLASS = "radar"
RISK_CLASS = "risk"


def is_authorized(channel: str, principal: Principal) -> bool:
    """Whether ``principal`` may receive ``channel``."""
    if len(channel) > MAX_CHANNEL_LENGTH or _WILDCARD_CHARS & set(channel):
        return False
    if channel in _PUBLIC_EXACT or _MARKET_RE.match(channel):
        return True
    match = _ORG_RE.match(channel)
    if match is None:
        return False
    try:
        org_id = uuid.UUID(match.group(1))
    except ValueError:
        return False
    return principal.membership(org_id) is not None


def throttle_class(channel: str) -> str:
    """The ARCHITECTURE.md §5.2 throttle bucket for ``channel``.

    Risk events are deliberately un-throttled (0 ms): a coalesced risk event is
    a risk event the trader saw late, and lateness there is the failure mode
    the whole system exists to avoid.
    """
    if channel.startswith(MARKET_PREFIX):
        return PRICE_CLASS
    if channel == RADAR_CHANNEL:
        return RADAR_CLASS
    return RISK_CLASS
