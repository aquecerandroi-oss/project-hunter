"""Two of the three meme series: curve snapshots and trades (the per-minute
features moved to ``meme_features.py`` when ``0023`` grew them past this file's
line budget).

DATABASE.md §33 (revision ``0021_meme_radar``). All three are **global** (§1.1)
and all three are **RANGE-partitioned by month** (§1.3), which is the arithmetic
and not a preference:

- ``meme_curve_snapshots`` — the free REST budget is 60 requests/60 s, so the
  ceiling of this table is 60 rows/minute ≈ **31 M rows/year** even before the
  RPC reconciliation adds its own;
- ``meme_features_1m`` — one row per tracked mint per closed minute; at the
  default cap of 120 tracked mints that is ~63 M rows/year;
- ``meme_trades`` — written since T4.2c by the ``swap-api`` tape puller
  (``source = 'swap_api'``; the PumpPortal trade channel is paid and the on-chain
  decoder is still T4.2b), per-transaction events that could not be the one table
  rebuilt later to gain a partition key (§15.2: the partition column must be in
  the PK, so partitioning after the fact rebuilds the table).

Every partition column is **first in the primary key** (§15.2), and for
``meme_features_1m`` that is also the order the radar reads in: "the last closed
minute across every tracked mint" is a prefix scan, never a sort.

Retention is **90 days for every one of them and identical for graduated and
non-graduated mints** (``MEME_RETENTION_DAYS``, T4-MEME-RADAR.md §8 decision 2 —
Astra rejected keeping only ``complete = true`` because selecting on success after
the fact deletes the controls and poisons every later comparison). It is executed
by dropping whole monthly partitions (``infra/scripts/prune_partitions.py``), not
by ``DELETE``, which is the reason these tables need no ``DELETE`` grant at all.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    Index,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base

MCAP_SOL_EXPRESSION = "(virtual_sol_reserves / NULLIF(virtual_token_reserves, 0)) * total_supply"
"""Marginal price × total supply, in SOL — **always theoretical**
(T4-MEME-RADAR.md §4): it is not what selling everything would realize, because
the curve slips against its own seller.

``NULLIF`` keeps §15.8's rule intact. Market-data tables carry no CHECKs on
purpose — "a feed occasionally emits a zero, and a CHECK there turns strange data
into an ingestion failure" — and a plain division would do worse than a CHECK: it
would raise ``division by zero`` inside the insert. A zero reserve yields a NULL
market cap and the row still lands."""


class MemeCurveSnapshot(Base):
    """One point-in-time read of one bonding curve, from one source."""

    __tablename__ = "meme_curve_snapshots"
    __table_args__ = (
        Index("ix_meme_curve_snapshots_mint_observed", "mint", "observed_at"),
        CheckConstraint(
            "char_length(mint) > 0 AND char_length(source) > 0",
            name="provenance_is_not_empty",
        ),
        CheckConstraint("slot IS NULL OR slot >= 0", name="slot_is_not_negative"),
        {"postgresql_partition_by": "RANGE (observed_at)"},
    )

    observed_at: Mapped[datetime] = mapped_column(primary_key=True)
    """When the **source** says the state was true (the REST mirror's
    ``updated_at``, the RPC read's slot time). The partition key, and first in the
    PK because §15.2 requires it and because every range read is on it."""

    mint: Mapped[str] = mapped_column(Text, primary_key=True)

    source: Mapped[str] = mapped_column(Text, primary_key=True)
    """``pumpfun_rest`` | ``solana_rpc`` | ``pumpportal_ws``. In the key, not
    beside it: the REST mirror and the chain read of the same instant are two
    observations, and collapsing them would make one silently overwrite the other
    — the whole point of reconciling them (T4-MEME-RADAR.md §2: never a single
    source of truth for anything the scanner decides)."""

    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
    """When **we** could have acted on it — the ``observed_at``/``available_at``
    split of §18.2. A decision at 10:00 cannot be explained by a read that
    arrived at 10:02."""

    virtual_sol_reserves: Mapped[Decimal]
    virtual_token_reserves: Mapped[Decimal]
    real_sol_reserves: Mapped[Decimal]
    real_token_reserves: Mapped[Decimal]
    total_supply: Mapped[Decimal]
    """Human units, converted once at the T4.1 normalize boundary."""

    complete: Mapped[bool]
    """The curve is finished. Graduation is ``complete`` **and**
    ``real_token_reserves = 0`` (T4-MEME-RADAR.md §3, Astra's correction), never a
    SOL threshold — and migrating to PumpSwap is a *third*, separate event, which
    is why it lives on ``meme_tokens`` and not here."""

    mcap_sol: Mapped[Decimal | None] = mapped_column(Computed(MCAP_SOL_EXPRESSION, persisted=True))
    """Generated by the database, written by nobody. A producer-computed copy
    could disagree with the reserves sitting next to it, and "a copy that can
    disagree with its source is worse than no copy" (§18.2). The API reads it."""

    slot: Mapped[int | None] = mapped_column(BigInteger)
    commitment: Mapped[str | None] = mapped_column(Text)
    """``confirmed`` | ``finalized`` for an RPC read; NULL for the REST mirror,
    which states no finality at all. Declared rather than assumed (Astra's
    MUST-FIX 2 asks for finality on every on-chain read)."""

    mayhem_enabled: Mapped[bool | None]
    mayhem_state: Mapped[str | None] = mapped_column(Text)
    mayhem_mode: Mapped[str | None] = mapped_column(Text)
    """As the source reported them **at this instant**. Mutable state needs
    history (A4.1b §6): retro-applying today's agent state to a past minute is
    exactly the research error the snapshot exists to prevent."""


class MemeTrade(Base):
    """A single buy/sell against a curve, from the ``swap-api`` tape (T4.2c)."""

    __tablename__ = "meme_trades"
    __table_args__ = (
        Index("ix_meme_trades_mint_block_time", "mint", "block_time"),
        CheckConstraint("side IN ('buy', 'sell')", name="side_is_a_known_label"),
        CheckConstraint(
            "commitment IS NULL OR commitment IN ('confirmed', 'finalized')",
            name="commitment_is_a_known_label",
        ),
        CheckConstraint("event_index >= 0", name="event_index_is_not_negative"),
        CheckConstraint(
            "(outer_ix_index IS NULL OR outer_ix_index >= 0) "
            "AND (inner_ix_index IS NULL OR inner_ix_index >= 0)",
            name="instruction_indexes_are_not_negative",
        ),
        CheckConstraint("slot >= 0 AND sol_lamports >= 0", name="chain_counters_are_not_negative"),
        {"postgresql_partition_by": "RANGE (block_time)"},
    )

    block_time: Mapped[datetime] = mapped_column(primary_key=True)
    """The block's time — never ``received_at`` (T4-MEME-RADAR.md §5). Partition
    key, therefore first in the PK (§15.2)."""

    signature: Mapped[str] = mapped_column(Text, primary_key=True)

    event_index: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    """The ordinal of this decoded trade **event within the transaction**, and the
    half of the dedupe key that Astra's MUST-FIX 2 says was missing: keyed on
    ``(signature, ts)`` alone, two distinct trades inside one transaction were one
    row, and the second was lost to ``ON CONFLICT DO NOTHING`` — the same silence
    that cost the T3.62 replay 24 receipts (§30). ``outer_ix_index`` and
    ``inner_ix_index`` sit beside it as provenance; the *key* is one integer
    because a CPI and the log of the same fill must count once (A4.1b §6)."""

    mint: Mapped[str] = mapped_column(Text)
    slot: Mapped[int] = mapped_column(BigInteger)
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
    outer_ix_index: Mapped[int | None] = mapped_column(SmallInteger)
    inner_ix_index: Mapped[int | None] = mapped_column(SmallInteger)

    trader: Mapped[str] = mapped_column(Text)
    """The economic authority of the operation, resolved per instruction — **not**
    the fee payer and not the first signer. A4.1b §5.2 measured a real Mayhem buy
    whose agent wallet was ``signer: false`` and came from a lookup table: a
    fee-payer filter would have labelled that purchase organic."""

    side: Mapped[str] = mapped_column(Text)
    sol_lamports: Mapped[int] = mapped_column(BigInteger)
    """Base units, as an exact integer. The quote side of a trade is counted in
    lamports on chain, and a float conversion at the boundary is the one thing
    every layer of this project refuses (§1)."""

    token_amount: Mapped[Decimal]
    price: Mapped[Decimal]
    """``sol_amount / token_amount`` at event time, never recalculated later."""

    quote_mint: Mapped[str] = mapped_column(Text)
    token_decimals: Mapped[int] = mapped_column(SmallInteger)
    """Explicit, because the adapter refuses a non-SOL quote today and the day it
    stops refusing, a row that did not say which quote it was would be
    unreadable (Astra's MUST-FIX 2)."""

    commitment: Mapped[str | None] = mapped_column(Text)
    """``confirmed`` | ``finalized`` when the producer states finality (an
    on-chain decoder); ``NULL`` when it states none — ``swap_api``, the producer
    that actually landed (T4.2c, ``0023``), the same word
    ``meme_curve_snapshots.commitment`` uses for the REST mirror."""
    is_mayhem_agent: Mapped[bool | None]
    """``NULL`` = attribution incomplete, ``false`` **only** after the operation
    was attributed to some other trader (A4.1b §6). The three organic metrics may
    only be computed over ``is_mayhem_agent IS FALSE``; a NULL is pending
    coverage, never an organic trade."""

    source: Mapped[str] = mapped_column(Text)
