"""Which instrument names a window's numbers — and what the chain says when
none of them does (T4.41).

Three sources can fill ``buys``/``sells``/``unique_buyers``/``curve_volume``/
``net_sol_flow`` of a 60 s window, and until the T4.41 they were tried in the
wrong order. KB-0116 (16/09) compared each of them, minute by minute, with the
one number the chain itself states — the delta of ``real_sol_reserves`` of the
bonding curve:

* ``activity_1m`` (the batch route's own ``1m`` window): sign agreement
  **85,7 %**, median ratio **1,00**, corr 0,835 over n = 6 688;
* ``swap_api_trades`` (the per-mint tape folded over the minute): sign
  agreement **34,9 %**, median ratio **0,00** over n = 1 820 — the puller
  brings one page a minute and the fold credited the whole minute to it.

So :func:`choose_tape` puts the batch first, lets the per-mint tape fill only
what the batch did not cover (and always lend the creator columns, which no
batch can say), and names the chain's own delta (:func:`chain_flow`) as the
flow's third source, with the counts left unknown.

Pure: no IO, no clock read. Non-anticipation is decided by ``received_at``
here as everywhere else in the fold — a photo that reached us after the
instant judged is not an input of it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal

from hunter_indicators.meme.fast import FastPoint
from hunter_meme_worker.features_tape import MONEY_QUANTUM, TapeMinute

CHAIN_DELTA = "chain_delta"
"""``tape_source`` (``0032``, ``T4.41``) for the flow the **chain** states:
the delta of ``real_sol_reserves`` between two curve photos of the last ~60 s.
**Not written to the two series yet** — see :class:`ChainFlow`."""
BUYERS_UNKNOWN = "buyers_unknown"
"""The gate's existing word for "nobody counted the buyers of this window"
(``rules_criteria.py``): what a ``chain_delta`` flow leaves unsaid — a delta of
reserves is a net number of SOL, never a number of people or of legs."""


@dataclass(frozen=True, slots=True)
class ChainFlow:
    """The flow of the last ~60 s read off the **chain** instead of off a tape:
    ``real_sol_reserves`` of the newest curve photo minus the same figure of
    the newest photo at least ``window_s`` older, both received by the instant
    judged.

    It is a **net number of SOL and nothing else**: buys, sells and unique
    buyers stay unknown (``BUYERS_UNKNOWN``) — a delta of reserves counts no
    people and no legs, and the vaivém inside one 12 s photo interval cancels.

    **Not persisted yet, on purpose.** ``meme_features_15s`` /
    ``meme_features_1m`` carry two CHECKs that a ``chain_delta`` row would
    break: ``tape_source_is_consistent`` (``0032``) admits only
    ``swap_api_trades``/``activity_1m`` *and* demands ``buys_*`` not null, and
    ``tape_is_null_with_a_reason`` (``0023``) ties ``net_sol_flow_*`` to
    ``buys_*`` in the same nullity. Writing this flow with its counts null
    needs a migration that widens the label set and splits the flow out of the
    tape's all-or-nothing group; until then the number is computed, named and
    handed to the caller in :class:`TapeChoice`, the row stays as it was, and
    no reader is told the tape said something it did not."""

    net_sol_flow: Decimal
    as_of: datetime
    """The newest photo's ``observed_at`` — the instant the window ends."""
    window_s: int
    """Seconds actually spanned by the two photos (never the nominal 60)."""
    points: int
    source: str = CHAIN_DELTA


def chain_flow(
    points: Sequence[FastPoint],
    *,
    as_of: datetime,
    window_s: int = 60,
    max_age_s: float = 60.0,
) -> ChainFlow | None:
    """Δ ``real_sol_reserves`` over the last ``window_s`` seconds, or ``None``.

    Non-anticipation like every other fold here: a photo received after
    ``as_of`` is not an input. ``None`` when there is no photo with real SOL,
    when the newest one is older than ``max_age_s`` (the delta would not
    describe *this* instant), or when no photo sits between ``window_s`` and
    ``2 * window_s`` before it (the reference would stretch the window past
    what the column claims)."""
    by_instant: dict[datetime, FastPoint] = {}
    for point in sorted(points, key=lambda p: (p.observed_at, p.received_at)):
        if point.received_at > as_of or point.observed_at > as_of:
            continue
        if point.real_sol_reserves is None:
            continue
        by_instant[point.observed_at] = point
    if not by_instant:
        return None
    usable = [by_instant[t] for t in sorted(by_instant)]
    newest = usable[-1]
    if as_of - newest.observed_at > timedelta(seconds=max_age_s):
        return None
    cutoff = newest.observed_at - timedelta(seconds=window_s)
    floor = newest.observed_at - timedelta(seconds=2 * window_s)
    references = [p for p in usable if floor < p.observed_at <= cutoff]
    if not references:
        return None
    reference = references[-1]
    assert newest.real_sol_reserves is not None
    assert reference.real_sol_reserves is not None
    net = (newest.real_sol_reserves - reference.real_sol_reserves).quantize(
        MONEY_QUANTUM, ROUND_HALF_EVEN
    )
    return ChainFlow(
        net_sol_flow=net,
        as_of=newest.observed_at,
        window_s=int((newest.observed_at - reference.observed_at).total_seconds()),
        points=len(usable),
    )


@dataclass(frozen=True, slots=True)
class TapeChoice:
    """Which instrument named the window's numbers (T4.41), and the reason the
    row keeps when none did."""

    minute: TapeMinute | None
    chain: ChainFlow | None
    absence: str


def _with_creator(batch: TapeMinute, tape: TapeMinute | None) -> TapeMinute:
    """The batch's counts with the per-mint tape's creator booleans: the batch
    does not say *who* traded, and ``meme_trades`` is the only source that
    does (KB-0116 §6). The numbers and ``tape_source`` stay the batch's."""
    if tape is None or tape.creator_net_seller is None:
        return batch
    return replace(
        batch, creator_sold=tape.creator_sold, creator_net_seller=tape.creator_net_seller
    )


def choose_tape(
    *,
    batch: TapeMinute | None,
    tape: TapeMinute | None,
    chain: ChainFlow | None = None,
    absence: str,
) -> TapeChoice:
    """The precedence KB-0116 measured, inverted from ``0032``'s (T4.41).

    1. **the batch** (``activity_1m``) — 96 % of the rows already came from it
       and it tracks the chain (sign 85,7 %, median ratio 1,00, corr 0,835);
    2. the **per-mint tape** (``swap_api_trades``) only when the batch did not
       cover that mint in that minute — it still names *who* traded, which is
       all the creator columns have;
    3. the **chain** (:class:`ChainFlow`) for the flow alone when neither
       covered — buys/sells/unique buyers stay unknown (``BUYERS_UNKNOWN``).

    ``tape_source`` on the row says which of the two tapes it was; the chain's
    flow rides in :attr:`TapeChoice.chain` and is not written to the series yet
    (the CHECKs in :class:`ChainFlow`'s docstring)."""
    if batch is not None:
        return TapeChoice(minute=_with_creator(batch, tape), chain=None, absence=absence)
    if tape is not None:
        return TapeChoice(minute=tape, chain=None, absence=absence)
    return TapeChoice(minute=None, chain=chain, absence=absence)
