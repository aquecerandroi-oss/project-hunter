"""Apply the transaction's own ``CompleteEvent`` to the curve readings of its swap records (wave 1b).

The log reader collects, per transaction, the swap records, the pump trade events it had to refuse
(they keep their place: a refused trade can be the one a ``CompleteEvent`` closes) and the
``CompleteEvent`` list; this module turns that into the final ``curve_completion`` of each record and
the count of orphan ``CompleteEvent`` (rule: :mod:`hunter_exchanges.pumpfun.curve_completion`). Pure.
"""

from __future__ import annotations

import struct
from collections.abc import Sequence
from dataclasses import replace

from hunter_exchanges.pumpfun.curve_completion import CurveCompletion, contradicted_ordinals
from hunter_exchanges.pumpfun.swap_record import SwapRecord
from hunter_exchanges.pumpfun.trade_event_codec import decode_trade_event

__all__ = ["reconcile_completion", "refused_trade_mint"]


def refused_trade_mint(payload: bytes) -> str | None:
    """The mint of a pump trade event that was refused, ``None`` when it does not even decode."""
    try:
        return decode_trade_event(payload).mint
    except (ValueError, struct.error):
        return None


def reconcile_completion(
    swaps: Sequence[SwapRecord],
    refused_trades: Sequence[tuple[int, str | None]],
    completes: Sequence[tuple[int, str]],
) -> tuple[list[SwapRecord], int]:
    """``(swaps with every contradicted curve reading turned ``unknown``, orphan CompleteEvents)``."""
    trades: list[tuple[int, str | None, CurveCompletion | None]] = [
        (s.event_ordinal, s.mint or "", s.curve_completion or "unknown")
        for s in swaps
        if s.venue == "curve"
    ]
    trades += [(n, mint, None) for n, mint in refused_trades]
    bad, orphans = contradicted_ordinals(trades, completes)
    out = [
        replace(s, curve_completion="unknown")
        if s.venue == "curve" and s.event_ordinal in bad
        else s
        for s in swaps
    ]
    return out, orphans
