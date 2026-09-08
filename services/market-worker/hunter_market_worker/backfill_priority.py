"""Fair share of the per-cycle history budget across markets (T3.7d).

**Incident.** `.claude/state/notes-T3.7b-diag.md` (2026-09-08): BTCUSDT and
UNIUSDT sat at attempts=0 for 8h30 while `MARSCOINUSDT` — listed on the shard
mid-request, with four pre-listing windows the exchange can never fill —
monopolized every one of the shard's six per-cycle history slots, forever.
The direct cause was `recovery_queries.pending_gaps`' single global
``ORDER BY gap_end DESC`` over the whole history tier: whichever market's
oldest hole happens to carry the newest `gap_end` wins every slot, every
cycle, with no notion of "which market this row belongs to" — a second
market's backlog, however large, never gets served while the first has any
row left. T3.7d's item 1 (`unrecoverable`/`before_listing`) closes the direct
cause; this module closes the structural one, so a market that legitimately
has a bigger backlog (no pre-listing rows at all, just more history) cannot
do the same thing MARSCOINUSDT did by accident.

**Round robin, not weighted-by-request.** ``ingestion_gaps`` deliberately
carries no column that says who asked for a gap
(`recovery_queries.pending_gaps` docstring, T2.9c) — a gap the live tier
itself creates can age into history with nobody ever having published
``market.backfill.requested``. Weighting the budget by "this gap came from an
explicit request" would need that column, which is a schema change out of
this task's scope (`infra/migrations/**` is off limits here; `ingestion_gaps`
has no CHECK on its columns, but a new *column* still needs a migration).
Round robin needs nothing new: it only requires knowing which market an open
gap belongs to, which ``ingestion_gaps.market_id`` already says, and it
already guarantees the property the incident violated — one market can never
own more than its fair share of the six slots while another with open history
gaps gets zero.

**Where the SQL ends and this module begins.** `recovery_queries.history_candidates`
fetches, per market, its own top ``limit`` candidates ordered `gap_end DESC`
(never more than ``limit`` rows for one market — a single market can never
need more than the whole shared budget, so asking Postgres for more would
only waste the round trip). This module is the pure interleaving of those
already-ordered, already-grouped rows into the final pick list, kept apart
from the query for the same reason `backfill_plan.py` keeps its own arithmetic
pure and sessionless: every hard decision here is cheap to pin with a table
test.
"""

from __future__ import annotations

from typing import Any


def interleave(grouped: dict[Any, list[tuple[Any, Any]]], limit: int) -> list[tuple[Any, Any]]:
    """One row from every market with anything left, round after round, until
    ``limit`` rows are picked or every market's own queue is drained.

    ``grouped`` maps ``market_id`` -> its own candidate ``(gap_id, market_id)``
    rows, already in the order they should be served *within* that market
    (``gap_end DESC``, the same intra-market priority `pending_gaps` always
    used). The outer order — which market goes first in a round — is the
    dict's own iteration order; fairness does not depend on it, only on the
    rule that no market gets a second slot before every other market with
    work left gets a first one in the same round.

    A market that runs out mid-way (fewer open history gaps than its
    round-robin share) is simply skipped from then on — its leftover slots go
    to whichever markets still have rows, rather than being wasted. That is
    what turns "two markets, twelve gaps each, six slots -> three each" and
    "twenty gaps and two gaps, six slots -> four and two" into the same
    algorithm.
    """
    if limit <= 0 or not grouped:
        return []
    queues = {market_id: list(rows) for market_id, rows in grouped.items() if rows}
    order = list(queues.keys())
    picked: list[tuple[Any, Any]] = []
    while len(picked) < limit and queues:
        for market_id in order:
            if market_id not in queues:
                continue
            picked.append(queues[market_id].pop(0))
            if not queues[market_id]:
                del queues[market_id]
            if len(picked) >= limit:
                break
    return picked
