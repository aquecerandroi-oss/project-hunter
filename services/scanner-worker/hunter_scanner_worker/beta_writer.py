"""One immutable revision of one market's beta, written or recognised as a retry.

``market_betas`` (DATABASE.md §18.6) is append-only with exactly one exception:
``superseded_at``, ``NULL`` -> value, once. Everything this module does follows
from that plus two keys:

- ``uq_market_betas_revision`` is ``(market_id, as_of, beta_version,
  input_digest)`` — a byte-identical **retry** collides and is a no-op, a real
  **recomputation** lands as a new revision. So the digest has to cover the
  reference's identity, the effective inputs and the quality evidence, never
  just the coefficients: a rerun that a backfill turned from ``gaps`` into a
  beta must not look like the run it corrects;
- ``uq_market_betas_current`` is ``(market_id, as_of, beta_version) WHERE
  superseded_at IS NULL`` — inserting a new revision without retiring the old
  one **in the same transaction** is refused by the database, not by a
  convention.

Hence the order below: *recognise* first, then retire, then insert. Recognising
first is what stops a rerun that changed nothing from retiring the revision a
decision may already have cited — the insert would then be a no-op and the
market would be left with no revision in force at that cut at all.

**Declared limit.** A digest that has already existed at this cut is treated as
a retry even when it was superseded since, because reviving a retired revision
is what the immutability trigger exists to refuse. Getting there needs a
recomputation to swing back to a byte-identical earlier answer, which means
candles that were persisted and then vanished; the honest cure is a new cut, one
hour later, not an edit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import orjson
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hunter_core.db.models.betas import MarketBeta
from hunter_core.domain.types import uuid7
from hunter_core.strategies.canonical import canonical_json, params_hash

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_indicators.beta import BetaEstimate

__all__ = ["INSERTED", "SUPERSEDED", "UNCHANGED", "input_digest", "write_revision"]

INSERTED = "inserted"
SUPERSEDED = "superseded"
"""Inserted **and** the previous revision of the same cut was retired for it."""
UNCHANGED = "unchanged"
"""This exact revision already exists: the rerun writes nothing."""

_CURRENT = text(
    "SELECT id FROM market_betas WHERE market_id = :market AND as_of = :as_of "
    "AND beta_version = :version AND superseded_at IS NULL FOR UPDATE"
)
_SAME_DIGEST = text(
    "SELECT 1 FROM market_betas WHERE market_id = :market AND as_of = :as_of "
    "AND beta_version = :version AND input_digest = :digest"
)
_RETIRE = text("UPDATE market_betas SET superseded_at = :now WHERE id = :id")


def input_digest(estimate: BetaEstimate, *, reference_market_id: UUID) -> str:
    """What separates a retry from a recomputation, hashed once.

    ``BetaEstimate.as_wire()`` is already the canonical serialisation of the
    whole answer — coefficients, window, ``n``, ``contiguous_bars``,
    ``last_pair_end``, validity, reason and the parameter set — so the digest is
    that, plus the reference's **id**. The wire form names the reference by
    symbol, and a symbol is not an identity: the same ``BTCUSDT`` on another
    venue is another series.
    """
    return params_hash({"reference_market_id": reference_market_id, **estimate.as_wire()})


def _json(payload: Any) -> Any:
    """The canonical bytes of ``payload``, decoded into JSONB-ready values.

    Going through :func:`canonical_json` rather than a bespoke encoder is what
    keeps the stored JSON identical to the bytes the digest was taken over —
    ``Decimal`` as a normalised string, timestamps as UTC ISO-8601 with ``Z``.
    """
    return orjson.loads(canonical_json(payload))


def _row(
    estimate: BetaEstimate,
    *,
    market_id: UUID,
    reference_market_id: UUID,
    now: datetime,
    digest: str,
) -> dict[str, Any]:
    wire = estimate.as_wire()
    return {
        "id": uuid7(),
        "market_id": market_id,
        "reference_market_id": reference_market_id,
        "as_of": estimate.as_of,
        "window_start": estimate.window_start,
        "window_end": estimate.window_end,
        "input_start": estimate.input_start,
        "last_pair_end": estimate.last_pair_end,
        "valid_until": estimate.valid_until,
        "computed_at": now,
        "available_at": now,
        "beta_version": estimate.version,
        "estimator": estimate.estimator.value,
        "beta": estimate.beta,
        "alpha": estimate.alpha,
        "r_squared": estimate.r_squared,
        "n": estimate.n,
        "contiguous_bars": estimate.contiguous_bars,
        "valid": estimate.valid,
        "reason": estimate.reason,
        "input_digest": digest,
        "estimate": _json(wire),
        "params": _json({"params": wire["params"], "numeric": wire["numeric"]}),
    }


async def write_revision(
    session: AsyncSession,
    estimate: BetaEstimate,
    *,
    market_id: UUID,
    reference_market_id: UUID,
    now: datetime,
) -> str:
    """Store ``estimate`` as a revision of this cut. Returns what happened.

    ``available_at`` and ``computed_at`` are the caller's clock, not the
    server's: the run's own instant is what a replay has to be able to
    reproduce, and ``now()`` would make two rows of the same pass disagree by
    milliseconds for no reason anybody could use.
    """
    keys = {
        "market": market_id,
        "as_of": estimate.as_of,
        "version": estimate.version,
    }
    digest = input_digest(estimate, reference_market_id=reference_market_id)
    if await session.scalar(_SAME_DIGEST, {**keys, "digest": digest}) is not None:
        return UNCHANGED
    current = await session.scalar(_CURRENT, keys)
    if current is not None:
        await session.execute(_RETIRE, {"id": current, "now": now})
    await session.execute(
        pg_insert(MarketBeta).values(
            _row(
                estimate,
                market_id=market_id,
                reference_market_id=reference_market_id,
                now=now,
                digest=digest,
            )
        )
    )
    return SUPERSEDED if current is not None else INSERTED
