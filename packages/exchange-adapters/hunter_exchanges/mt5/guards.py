"""Pre-send invariants that are the adapter's own (contract §12: I-X-2, I-SL-1, I-SL-4, I-SL-6).

Pure functions over already-converted ``Decimal`` models. They return a *named refusal* or
``None``; the adapter turns a refusal into :class:`~hunter_exchanges.mt5.errors.Mt5NotSent`
before ``order_send`` is ever called.

**Netting stop inheritance** (MetaTrader 5 help, "Rules of Stop Loss and Take Profit
inheritance (netting)"; design §2.2). On a netting/exchange account an order that *increases or
inverts* the position replaces the position's ``sl``/``tp`` with the order's own — and zero
erases the stop. A partial close does not touch ``sl``/``tp``; a full close deletes them with
the position. So:

=========  ====================================================  ==========================
effect     what the server does to the stop                      this guard
=========  ====================================================  ==========================
OPEN       a new position gets the order's ``sl``/``tp``         allows (engine check 15)
INCREASE   the order's ``sl`` replaces the position's            refuses ``sl = 0`` and a
                                                                 looser ``sl``
INVERT     a new opposite position gets the order's ``sl``       refuses ``sl = 0``
REDUCE     unchanged                                             never refuses on the stop
CLOSE      stop deleted with the position                        never refuses on the stop
=========  ====================================================  ==========================
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from enum import StrEnum

from .convert import OffGridError, to_float_on_grid
from .models import EntryRequest, Mt5Position, Mt5SymbolSpec, Side, SltpRequest


class EntryEffect(StrEnum):
    OPEN = "open"
    INCREASE = "increase"
    INVERT = "invert"
    REDUCE = "reduce"
    CLOSE = "close"


def entry_effect(request: EntryRequest, positions: Sequence[Mt5Position]) -> EntryEffect:
    """What the request does to the (single, netting) position on its symbol."""
    current = next((p for p in positions if p.symbol == request.symbol), None)
    if current is None:
        return EntryEffect.OPEN
    if request.side is current.side:
        return EntryEffect.INCREASE
    if request.volume < current.volume:
        return EntryEffect.REDUCE
    if request.volume == current.volume:
        return EntryEffect.CLOSE
    return EntryEffect.INVERT


def would_delete_stop(request: EntryRequest, positions: Sequence[Mt5Position]) -> bool:
    """True iff the request would erase the stop of a position (increase/invert with ``sl = 0``)."""
    effect = entry_effect(request, positions)
    return effect in (EntryEffect.INCREASE, EntryEffect.INVERT) and request.sl == 0


def _looser(side: Side, candidate: Decimal, reference: Decimal) -> bool:
    """Is ``candidate`` a wider (less protective) stop than ``reference`` for ``side``?"""
    return candidate < reference if side is Side.BUY else candidate > reference


def entry_stop_refusal(request: EntryRequest, positions: Sequence[Mt5Position]) -> str | None:
    """``would_delete_stop`` or ``would_loosen_stop``; ``None`` if the stop is not endangered."""
    if would_delete_stop(request, positions):
        return "would_delete_stop"
    if entry_effect(request, positions) is EntryEffect.INCREASE:
        current = next(p for p in positions if p.symbol == request.symbol)
        if current.has_stop and _looser(current.side, request.sl, current.sl):
            return "would_loosen_stop"
    return None


def _on_grid(value: Decimal, tick: Decimal) -> bool:
    try:
        to_float_on_grid(value, tick)
    except OffGridError:
        return False
    return True


def sltp_refusal(
    request: SltpRequest,
    position: Mt5Position | None,
    spec: Mt5SymbolSpec,
    quote: tuple[Decimal, Decimal] | None,
) -> str | None:
    """Named refusal for a SLTP request, or ``None``. ``quote`` is ``(bid, ask)`` read just now.

    ``sl = 0`` is never sent (I-SL-1); levels sit on the tick grid; the request is never looser
    than the stop confirmed on the server nor than the caller's floor (I-SL-6); and it targets
    the *current* ticket of a position that is ours (I-SL-4). ``tp = 0`` is allowed.

    **The touch** (contract §4.2 ``floor_unplaceable``, §4.4): a long stop above ``bid - gap``
    (short: below ``ask + gap``; ``gap = trade_stops_level * point``) is on the wrong side - the
    level could not be placed, or would stop the position out at once. It is refused locally
    (``sl_wrong_side_of_touch``) instead of being sent to see what the server does; the same for
    a target (``tp_wrong_side_of_touch``). No usable quote, no send. R5 turns the refusal of a
    request that carries the floor into the ``floor_unplaceable`` state.
    """
    if request.sl <= 0:
        return "sl_missing"
    if position is None:
        return "position_not_found"
    if position.position_ticket != request.position_ticket:
        return "position_ticket_mismatch"
    if position.symbol != request.symbol:
        return "position_symbol_mismatch"
    if position.magic != request.magic:
        return "position_magic_mismatch"
    tick = spec.trade_tick_size
    if not _on_grid(request.sl, tick):
        return "sl_off_tick"
    if request.tp != 0 and not _on_grid(request.tp, tick):
        return "tp_off_tick"
    if position.has_stop and _looser(position.side, request.sl, position.sl):
        return "sl_looser_than_confirmed"
    if _looser(position.side, request.sl, request.floor_sl):
        return "sl_looser_than_floor"
    if quote is None:
        return "quote_unavailable"
    bid, ask = quote
    if bid <= 0 or ask <= 0:
        return "quote_invalid"
    gap = spec.trade_stops_level * spec.point
    long_ = position.side is Side.BUY
    if request.sl > bid - gap if long_ else request.sl < ask + gap:
        return "sl_wrong_side_of_touch"
    if request.tp != 0 and (request.tp < ask + gap if long_ else request.tp > bid - gap):
        return "tp_wrong_side_of_touch"
    return None
