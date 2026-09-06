"""R1 — replaying eight exit policies over the Lab's frozen entries (EXP-0004).

Research only. Reads ``agent_signals`` / ``signal_outcomes`` / ``candles`` /
``funding_rates`` and writes **nothing**: no table of the Lab is touched, no
episode slot is taken or re-armed, nothing is activated.

The point of the package is reuse. The exit rules are not written down again
here: an arm is a different :class:`~hunter_strategy_worker.walker.TrackingPlan`
folded by the very same :func:`~hunter_strategy_worker.walker.walk`, and the
money is closed by the very same :func:`~hunter_strategy_worker.settle.settle`
(and therefore the same funding resolver). The two rules that cannot be written
as a price level — ``INV-C`` and ``EXIT-CHAN`` — are evaluated by pure
observers in ``hunter_indicators.replay`` and handed to the walker as a pending
invalidation, so it is still the walker that decides when it is paid and with
which priority.
"""

from __future__ import annotations
