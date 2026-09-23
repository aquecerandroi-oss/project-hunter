"""The SQL-side twin of ``services/lab_signal_identity.compute_identity_key``
— T3.38a/T3.38c, split out of ``repositories/lab_signals.py`` in T4.82 when
that module passed the 350-line budget.

One responsibility: express, in SQL, the seven-field tuple that says "these
two rows decided on the same operation", so ``COUNT(DISTINCT ...)`` can group
by it inside Postgres instead of fetching the whole filtered dataset home and
hashing it in Python. Nothing here runs a query; it is one expression and the
four parts it is built from.
"""

from __future__ import annotations

from sqlalchemy import Numeric, Text, case, cast, func

from hunter_api.repositories.lab_common import DECISION_AT
from hunter_core.db.models.agents import AgentSignal, SignalOutcome
from hunter_core.db.models.markets import Market
from hunter_core.domain.enums import ShadowTrackingState

__all__ = ["IDENTITY_KEY_TEXT"]

_SOURCE_BAR_CLOSE_TEXT = func.coalesce(
    AgentSignal.supporting_features["observation_ts"].astext,
    cast(DECISION_AT, Text),
)
"""T3.38a: same fallback ``services/lab_signals.py``'s ``_to_out`` applies in
Python (``observation_ts``, else ``decision_at``) -- an SQL text expression so
``COUNT(DISTINCT ...)`` can group by it without pulling every row home."""

_EXIT_REASON_TEXT = case(
    (SignalOutcome.tracking_state == ShadowTrackingState.NO_ENTRY, SignalOutcome.no_entry_reason),
    (SignalOutcome.tracking_state == ShadowTrackingState.CENSORED, SignalOutcome.censored_reason),
    else_=cast(SignalOutcome.result, Text),
)
"""Mirrors ``services/lab_signals.py``'s ``_exit_reason``: the specific
no-entry/censored reason when there is one, ``result`` otherwise."""

_IDENTITY_NUMERIC = Numeric(28, 10)
"""Same scale as ``lab_signal_identity._DECIMAL_SCALE`` (``1e-10``, ten
decimal places) -- casting through this before ``::text`` (T3.38c finding 3)
means two numerically equal prices with a different number of trailing
zeros (``"1.16930116"`` vs ``"1.169301160"``) render identically here, the
same as ``Decimal.quantize`` does on the Python side."""

_IDENTITY_SEP = chr(31)
"""ASCII unit separator -- the SQL-side twin of
``lab_signal_identity._FIELD_SEP`` (T3.38c finding 4). Was ``"|"``, which
could not collide with the fields hashed here (none of them can contain a
pipe) but made this expression's raw text byte-different from the Python
hash input for no reason; ``chr(31)`` makes the two identical for a given
row, provable directly (``test_lab_signals_identity_api.py``)."""

IDENTITY_KEY_TEXT = func.concat(
    Market.symbol,
    _IDENTITY_SEP,
    _SOURCE_BAR_CLOSE_TEXT,
    _IDENTITY_SEP,
    cast(cast(SignalOutcome.virtual_entry, _IDENTITY_NUMERIC), Text),
    _IDENTITY_SEP,
    cast(cast(SignalOutcome.virtual_stop, _IDENTITY_NUMERIC), Text),
    _IDENTITY_SEP,
    cast(cast(SignalOutcome.exit_price, _IDENTITY_NUMERIC), Text),
    _IDENTITY_SEP,
    _EXIT_REASON_TEXT,
    _IDENTITY_SEP,
    cast(SignalOutcome.result, Text),
)
"""The SQL-side twin of ``lab_signal_identity.compute_identity_key`` -- same
seven-field tuple (T3.38c finding 2 adds ``virtual_stop``), concatenated (not
hashed: ``distinct_operations`` only needs to group rows, not reproduce the
API's opaque ``identity_key`` string) so it can be one indexed-free aggregate
instead of a Python fetch-and-hash of the whole filtered dataset. ``NULL``
handling is intentionally not symmetric with the Python side's ``_NULL``
sentinel here -- Postgres's ``concat()`` silently drops ``NULL`` arguments,
so a ``NULL`` price shifts the remaining text rather than leaving a visible
gap; that is fine for grouping (two rows with the same ``NULL`` pattern still
concatenate to the same text) but is why this expression is never hashed and
compared to the API's ``identity_key`` as anything other than the same raw
text for the *same* row (see the finding-4 integration test, which seeds a
row with every field populated precisely so no ``NULL`` is on the path)."""
