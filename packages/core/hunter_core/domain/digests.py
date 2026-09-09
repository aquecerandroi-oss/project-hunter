"""Canonical digests — a set written down so a key can be keyed on it.

There is exactly one today: the market list of a replay slice
(``replay_runs.markets_digest``, ``0018_replay_runs_slice_markets``,
DATABASE.md §30). It exists because a *slice* of a replay is a window **and** a
set of markets, and until ``0018`` the durable receipt was keyed only on the
window: four market slices of the same window collided under
``ON CONFLICT (run_id, window_from, window_to) DO NOTHING`` and three of them
were silently discarded (T3.62, concern 1 — 8 of 32 receipts survived).

**Why a digest and not the array itself.** A UNIQUE over ``text[]`` would work
in Postgres and be wrong in the only way that matters: array equality is
order-sensitive, so dispatching the same four markets in another order would be
another slice. The digest is defined over the *sorted* list, so the order the
markets happened to be dispatched in cannot create a second receipt for work
that already has one.

**The same function is written twice, on purpose** — here in Python, for the
writer, and as a frozen SQL expression in
``infra/migrations/ddl/replay_runs_slice_markets.py``, for the backfill and for
the trigger that refuses a digest which does not name its own markets. They are
a copy and never an import (the database's contract must not silently follow a
later edit to a Python constant, ``ddl/paper_geometry.py``), and
``test_migrations.py::test_0018_the_python_digest_and_the_sql_expression_are_one_function``
is what keeps the copy honest.

**Byte order, not the database's collation.** The SQL side sorts with
``COLLATE "C"`` and this side with :func:`sorted`, which compares code points;
for UTF-8 the two orders are the same sequence. Sorting with the database's
default collation instead would make the digest depend on ``lc_collate`` — the
same list would hash differently on two clusters, and a receipt written by one
would look like a new slice to the other.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any

MARKETS_DIGEST_SEPARATOR = "\n"
"""What joins the sorted keys before hashing.

A separator and not concatenation: ``("a", "bc")`` and ``("ab", "c")`` are two
different market sets and must not share a digest. Newline because a market key
is ``<exchange>:<symbol>`` (``binance:BTCUSDT``) and cannot contain one.
"""

MARKETS_DIGEST_PATTERN = "^[0-9a-f]{64}$"
"""Lower-case hex SHA-256 and nothing else.

The database carries this as a CHECK, which is what makes a placeholder
unrepresentable: ``'legacy'``, ``''`` and ``'none'`` are all refused, so no row
can claim a digest it does not have. The frozen copy of this string lives in
``ddl/replay_runs_slice_markets.py``.
"""

__all__ = [
    "MARKETS_DIGEST_PATTERN",
    "MARKETS_DIGEST_SEPARATOR",
    "markets_digest",
]


def markets_digest(markets: Iterable[Any]) -> str:
    """SHA-256 (hex) of the sorted market keys of one replay slice.

    Order-independent by construction, and free of any number: the input is a
    set of ``<exchange>:<symbol>`` strings, so no ``float`` and no ``Decimal``
    ever reaches a hash whose value a UNIQUE key depends on.

    Raises ``TypeError`` for a non-string member — a receipt keyed on the
    ``repr`` of some object would be a key nobody could reproduce — and
    ``ValueError`` for an empty list, which is the CHECK
    ``ck_replay_runs_a_slice_visited_a_market`` (§25.2) one layer up: a slice
    that visited no market has no receipt to write.

    Typed ``Iterable[Any]`` for the reason :func:`domain.types.to_money` is
    typed ``Any``: the guard below is a **runtime** check, and the callers it
    exists for are exactly the ones that are not type-checked (a list decoded
    from JSON, a row read back from psql). Declared ``Iterable[str]`` the check
    would be a tautology the type checker deletes, which is a guard that only
    holds where it was never needed.
    """
    ordered = sorted(markets)
    for market in ordered:
        if not isinstance(market, str):
            raise TypeError(
                f"markets_digest() takes market keys as str, not {type(market).__name__}"
            )
        if MARKETS_DIGEST_SEPARATOR in market:
            raise ValueError(f"a market key may not contain a newline: {market!r}")
    if not ordered:
        raise ValueError("markets_digest() needs at least one market: a slice visited one")
    joined = MARKETS_DIGEST_SEPARATOR.join(ordered)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
