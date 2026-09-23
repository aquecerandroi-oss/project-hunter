"""T4.80: the buy-count ceiling of the entry gate — one optional key,
``max_buys_1m``, off unless the set names it.

R65 (KB-0147, 87 real trades of 16–21/09/2026) found the only entry variable
with a repeated signal: launches whose last closed minute carried **at most**
25 buys reached the target 34 % of the time with a median MFE of +28,1 %,
against 20 % and +8,2 % above that line — "quem entra em lançamento menos
disputado ganha mais". The number was chosen looking at those same 87 trades,
so it is a hypothesis and not an estimate (R65 §7, Astra's own position), and
R67 (23/09/2026, 473 out-of-sample mints) did **not** confirm it (D = +0,0358,
95 % CI [−0,0575, +0,1355], p = 0,43 — *not confirmed*, not *refuted*). The
criterion therefore ships **absent** and KB-0147's standing advice is to leave
it that way; the switch exists for the day there is evidence, turned on per
set with ``meme_rule_set.py --set-param``. Writing the key on ``operator/5``/
``/6`` is not a shadow measurement — it refuses real entries.

``buys_1m`` is the count of buys of the 60 s ending at the decision instant —
``meme_features_1m.buys_1m`` on the closed-minute lane, ``buys_60s`` on the
15-second lane, and ``MintEventState.tape_minute(as_of)``'s own fold on the
event lane. All three already carry it on the ``GateRow``; none of them looks
past the instant being judged (``tape_for``/``activity_for`` both keep only
what had *reached us* by then). The two non-event lanes may, however, be
reading a window that **ended** a few seconds before the decision, when the
``activity_1m`` batch covered the mint (KB-0116's own precedence): that is
lag, never look-ahead.

Fail closed, like every other unknown in this gate: a tape that has not
covered the minute (``event_feed_warming``, ``no_trade_feed``, ``not_polled``)
is not "nobody bought" — it is ``buys_1m_unknown``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hunter_indicators.meme.rules import EntryFeatures, EntryGate

__all__ = ["REFUSAL_BUYS_ABOVE_MAX", "REFUSAL_BUYS_UNKNOWN", "buys_refusals"]

REFUSAL_BUYS_ABOVE_MAX = "buys_1m_above_max"
REFUSAL_BUYS_UNKNOWN = "buys_1m_unknown"


def buys_refusals(features: EntryFeatures, gate: EntryGate) -> list[str]:
    """T4.80: the ceiling on the minute's buy count, only when the gate asks.

    Inclusive: ``max_buys_1m = 25`` allows exactly 25 (R65's own "``buys_1m``
    ≤ 25"), and only 26 refuses.
    """
    if gate.max_buys_1m is None:
        return []
    if features.buys_1m is None:
        return [REFUSAL_BUYS_UNKNOWN]
    if features.buys_1m > gate.max_buys_1m:
        return [REFUSAL_BUYS_ABOVE_MAX]
    return []
