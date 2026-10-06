"""Was the bonding curve complete AT a trade event? (wave 1b of H-030, migration censoring §3.1)

**What the chain gives.** The post-upgrade pump ``TradeEvent`` has no ``complete`` flag: the on-chain
IDL lists it only on the ``BondingCurve`` account, which could only be read *later* (look-ahead if
applied back to an older trade). The event does carry ``real_token_reserves`` AFTER the trade, and a
buy that drains the curve (``real_token_reserves == 0``) is followed, inside the same transaction, by
the program's own ``CompleteEvent`` for the same mint. After that no curve trade of the mint can
succeed (it reverts), so the completing trade is also the last curve event the mint will ever have.

**The rule** (a named tri-state, :data:`CurveCompletion`), per curve trade:

* ``complete``: a **buy** whose ``real_token_reserves`` is 0 AND the transaction's own
  ``CompleteEvent`` for the mint comes right after it (the last trade of that mint before the event);
* ``not_complete``: ``real_token_reserves > 0`` and no ``CompleteEvent`` closes it;
* ``unknown``: everything that breaks the pair — a **sell** reading 0 (a sell adds tokens, so 0 after
  it contradicts the rule), a draining buy with no ``CompleteEvent``, a ``CompleteEvent`` that closes
  a trade still holding real tokens (also an orphan: the draining trade is missing, so the reader
  reports a gap). Never resolved by picking a side.

Evidence, 05/10/2026. Stored and re-runnable (``tests/unit/test_curve_completion.py``, fixtures
``t1b_*``): 2 real completions (a buy reading 0 with the ``CompleteEvent`` next) and 1 real not-complete
predecessor of one of them, whose leftover tokens the draining buy took exactly. Seen in an ad-hoc scan
that was not stored: 3 more completions of the same shape and ~500 other curve trades above 0 with no
``CompleteEvent``.
Observed, not guaranteed by the protocol: a future program that completes a curve some other way
shows up as ``unknown`` (the ``CompleteEvent`` without a zero), not as a silent ``not_complete``.

Pure: no IO, no clock.
"""

from __future__ import annotations

import struct
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

from hunter_exchanges.pumpfun.solana_codec import b58encode

__all__ = [
    "COMPLETE_EVENT_DISCRIMINATOR",
    "CompleteEvent",
    "CurveCompletion",
    "completion_from_reserves",
    "decode_complete_event",
    "contradicted_ordinals",
]

COMPLETE_EVENT_DISCRIMINATOR: Final = bytes([95, 114, 97, 156, 212, 46, 152, 8])
_BODY_LENGTH: Final = 8 + 32 + 32 + 32 + 8 + 32

CurveCompletion = Literal["complete", "not_complete", "unknown"]


@dataclass(frozen=True, slots=True)
class CompleteEvent:
    user: str
    mint: str
    bonding_curve: str
    timestamp: int
    quote_mint: str


def decode_complete_event(raw: bytes) -> CompleteEvent:
    """Decode a ``CompleteEvent`` (144 bytes: discriminator, user, mint, bonding curve, timestamp,
    quote mint — the layout of every real event read on 05/10/2026). Any other length or
    discriminator raises ``ValueError``: an unknown layout is not a decode."""
    if raw[:8] != COMPLETE_EVENT_DISCRIMINATOR:
        raise ValueError("not a CompleteEvent (discriminator mismatch)")
    if len(raw) != _BODY_LENGTH:
        raise ValueError(f"CompleteEvent has {len(raw)} bytes, expected {_BODY_LENGTH}")
    return CompleteEvent(
        user=b58encode(raw[8:40]),
        mint=b58encode(raw[40:72]),
        bonding_curve=b58encode(raw[72:104]),
        timestamp=struct.unpack("<q", raw[104:112])[0],
        quote_mint=b58encode(raw[112:144]),
    )


def completion_from_reserves(is_buy: bool, real_token_reserves: int) -> CurveCompletion:
    """The reading of the event alone, before the ``CompleteEvent`` corroborates it."""
    if real_token_reserves > 0:
        return "not_complete"
    return "complete" if is_buy else "unknown"


def contradicted_ordinals(
    trades: Sequence[tuple[int, str | None, CurveCompletion | None]],
    completes: Sequence[tuple[int, str]],
) -> tuple[frozenset[int], int]:
    """``(ordinals of the curve readings the transaction's own CompleteEvent contradicts, orphans)``.

    ``trades`` is ``(ordinal, mint, reading)`` of EVERY pump ``TradeEvent`` seen, in event order: a
    trade that was refused (not a record) has ``reading`` ``None`` and a ``mint`` that is ``None``
    when it could not even be decoded, so it still holds its place. ``completes`` is ``(ordinal,
    mint)`` of every ``CompleteEvent``. A ``CompleteEvent`` closes the last trade before it that is
    its mint's (or may be: unknown mint); that trade must read ``complete``, and a trade that reads
    ``complete`` must be closed by one. If the closing trade was refused nothing is concluded about
    the records (the refusal is already a gap). A ``CompleteEvent`` with no trade before it that
    could be its own is an **orphan**: the draining trade is missing from what was read."""
    closing: set[int] = set()
    orphans = 0
    for at, mint in completes:
        earlier = [(n, r) for n, m, r in trades if n < at and (m is None or m == mint)]
        if not earlier:
            orphans += 1
            continue
        last, reading = max(earlier)
        closing.add(last)
        # A closing trade that still held tokens: the draining trade is missing from what was read.
        if reading == "not_complete":
            orphans += 1
    bad = frozenset(
        n
        for n, _, reading in trades
        if reading is not None
        and reading != "unknown"
        and (n in closing) != (reading == "complete")
    )
    return bad, orphans
