"""The one listing the Shadow Lab decides on.

Split out of :mod:`hunter_strategy_worker.consumer` (T3.83) purely to keep that
module under the file-size budget — this constant's own reasoning is long
enough on its own to justify a file, and it has exactly one reader.
"""

from __future__ import annotations

from hunter_core.domain.enums import MarketType

__all__ = ["DECISION_MARKET_TYPE"]

DECISION_MARKET_TYPE = MarketType.PERPETUAL
"""The only listing the Shadow Lab decides on (T3.73).

``markets`` holds two rows per symbol since T3.0b/T3.0c and the market-worker
publishes ``market.candles.closed`` for both (T3.0d), so the consumer — which
evaluates whatever bar arrives — started deciding on the ``spot`` row of a
symbol the day the spot path was switched on. That is not a second population,
it is the *same* bet counted twice (measured on the VPS on 2026-09-10: 179
(version, symbol, bar) triples decided on both rows), priced with a cost model
that does not exist there: ``funding_rates`` has no row for a spot market by
construction, so ``resolve_funding`` never establishes a cadence and every one
of the 133 terminal spot outcomes closed with ``r_multiple = NULL`` and
``funding_schedule_unknown``.

Perpetual-only is what the documents already say, in three places: PIPELINE §1d
item 1 (the spot path exists as the wallet's *execution price* while "todo o
resto do pipeline … continua raciocinando só sobre o perpétuo"), §1d item 7 (the
scanner drops spot ticks at the same kind of door, before coalescing) and
``replay/plan.py``, which has always restricted a replay to
``MarketType.PERPETUAL``. Nothing is lost on the wallet side: the execution
bridge maps a perpetual signal to its spot twin itself
(``bridge_universe.spot_pair_for``, scaling ``1000SHIBUSDT`` -> ``SHIBUSDT``),
so a paper signal never had to be born on a spot row to be executable on one.

Researching spot deliberately is a different task with its own cost model — it
would need a funding rule (zero, named, not merely unreadable), spot-native
assumed costs and a dedup rule for the perpetual twin. Refusing here is
fail-closed until that exists, never a silent omission: every refusal is
counted in ``hunter_shadow_bars_skipped_total{reason}``.
"""
