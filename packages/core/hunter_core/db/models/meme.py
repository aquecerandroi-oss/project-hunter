"""``meme_tokens`` and ``meme_ingest_gaps`` — the pump.fun dimension and its holes.

DATABASE.md §33 (revision ``0021_meme_radar``), ``docs/plans/T4-MEME-RADAR.md`` §5.
**Global tables** (§1.1): an on-chain token belongs to the chain, not to an
organization — no ``organization_id``, therefore no RLS, the shape ``markets``,
``market_regimes`` and ``market_breadth`` already have.

Three decisions live in this file rather than in prose:

- **identity is nullable and written once.** A migration frame can arrive for a
  mint whose ``create`` we never saw (a mandatory T4.1 scenario: the curve may
  predate the collector), and the migration frame carries no name, symbol,
  creator or creation time. So every identity column is nullable — ``NULL`` means
  *not observed yet*, never *empty* — and ``meme_tokens_identity_is_written_once``
  (``ddl/meme_radar.py``) refuses to change one that is already known, for every
  role including the owner. A later, poorer observation can never overwrite a
  richer earlier one, which is what "upsert once" has to mean when the producers
  disagree in *completeness* rather than in value.
- **``mayhem_enabled`` has no default.** ``NULL`` is "we do not know", and the
  absence of a JSON key is exactly that (A4.1b §3 measured a non-Mayhem coin by
  the *absence* of the field and only believed it after reading the on-chain
  boolean). A ``DEFAULT false`` would turn every unobserved token into a claimed
  negative — the correction Astra's MUST-FIX 2 asks for.
- **completion and migration are two events**, never one state
  (T4-MEME-RADAR.md §3): ``completed_at`` is the curve closing,
  ``migrated_at``/``migrated_pool`` is the pool moving to PumpSwap. Neither
  implies the other here, because the radar can start mid-life and see only the
  second.

``meme_ingest_gaps`` is **append-only and has no ``recovered_at``**: there is no
recovery path in this slice (no historical curve source, no trade feed), and a
column nobody writes would allege one exists. T4.2b brings the column with its
own revision.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import JSONB_EMPTY

MAYHEM_STATES = ("active", "paused", "completed", "unknown")
"""The four the screener's own bundle maps (A4.1b §4: the ``ended`` tab reads
``completed``, while ``active`` and ``paused`` keep their names) plus the honest
fourth: two sources disagreeing becomes ``unknown``, never a guess."""

MAYHEM_MODES = ("auto", "manual", "unknown")
"""A second axis, not a state: ``manual`` means the creator requests each
operation while direction and size stay random (A4.1b §2). Folding it into
``mayhem_state`` would lose ``manual + active``."""


class MemeToken(Base):
    """One pump.fun mint: its identity if we saw it, its lifecycle as it moves."""

    __tablename__ = "meme_tokens"
    __table_args__ = (
        Index("ix_meme_tokens_created_at", "created_at"),
        # The radar's list ("what was created recently") and, by riding the same
        # scan, its Mayhem filter. No partial Mayhem index exists on purpose:
        # nothing has measured a query that needs one, and a second btree on a
        # ~40k-rows/day write path is a cost paid for a plan nobody has seen
        # (§26.4's rule).
        Index("ix_meme_tokens_first_seen_at", "first_seen_at"),
        # Retention's own scan. It cannot use ``created_at``: that column is
        # nullable (identity may be unobserved) and retention must still be able
        # to age a row out. ``first_seen_at`` is NOT NULL by construction — we
        # cannot have a row without having seen something.
        CheckConstraint(
            "mayhem_state IS NULL OR mayhem_state IN ('active', 'paused', 'completed', 'unknown')",
            name="mayhem_state_is_a_known_label",
        ),
        CheckConstraint(
            "mayhem_mode IS NULL OR mayhem_mode IN ('auto', 'manual', 'unknown')",
            name="mayhem_mode_is_a_known_label",
        ),
        CheckConstraint(
            "NOT (mayhem_enabled IS FALSE AND mayhem_state IS NOT NULL)",
            name="a_disabled_token_has_no_agent_state",
        ),
        # A token measured as *not* Mayhem cannot carry an agent state: that pair
        # is two sources contradicting each other, and the honest write is
        # ``mayhem_state = 'unknown'`` with ``mayhem_enabled = NULL``.
        CheckConstraint(
            "migrated_at IS NULL OR migrated_pool IS NOT NULL",
            name="a_migration_names_its_destination",
        ),
        CheckConstraint(
            "(name IS NULL OR char_length(name) > 0) "
            "AND (symbol IS NULL OR char_length(symbol) > 0) "
            "AND (creator IS NULL OR char_length(creator) > 0) "
            "AND (uri IS NULL OR char_length(uri) > 0) "
            "AND (pool IS NULL OR char_length(pool) > 0)",
            name="an_observed_identity_is_not_empty",
        ),
        # ``NULL`` says "not observed"; the empty string would claim an identity
        # that is blank. The same argument ``no_entry_reason`` makes (§16.2).
        CheckConstraint(
            "char_length(first_seen_source) > 0 AND char_length(mint) > 0",
            name="provenance_is_not_empty",
        ),
    )

    mint: Mapped[str] = mapped_column(Text, primary_key=True)
    """The mint address — the natural key. No surrogate ``uuid`` here: every
    producer, every log line and every pump.fun URL names the mint, and a second
    identity would be a second truth to keep in step (§17.8)."""

    name: Mapped[str | None] = mapped_column(Text)
    symbol: Mapped[str | None] = mapped_column(Text)
    uri: Mapped[str | None] = mapped_column(Text)
    """Off-chain metadata (IPFS) as the create event gave it — labelled, never
    fetched and merged into the columns beside it."""

    creator: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime | None]
    """When the token was created. **Not a block time when it came from the WS**:
    PumpPortal's real-time frame carries no timestamp at all (verified against
    the T4.1 live capture), so the producer writes the frame's ``received_at``
    and this docstring is where that is declared instead of being passed off as
    chain time. A REST observation carries ``created_timestamp``, which is the
    provider's clock. ``NULL`` when only a migration was ever seen."""

    bonding_curve: Mapped[str | None] = mapped_column(Text)

    initial_virtual_sol_reserves: Mapped[Decimal | None]
    initial_virtual_token_reserves: Mapped[Decimal | None]
    """The create event's virtual reserves, in **human units** (SOL, 6-decimal
    tokens) — the normalize boundary of the T4.1 adapter converts once so no
    consumer reasons in lamports in one field and SOL in the next."""

    initial_real_token_reserves: Mapped[Decimal | None]
    """The **denominator of curve progress** (T4-MEME-RADAR.md §3, Astra's
    correction): ``1 - real_token_reserves / initial_real_token_reserves``.

    Written once, from the first observation whose ``real_sol_reserves`` is zero
    — a curve nobody has bought yet, so its real token reserves *are* the initial
    ones. That is an **observation**, not the 793,1 M constant every blog quotes:
    the plan forbids turning a third-party number into a constant, and a
    denominator we never observed leaves ``curve_progress_pct`` NULL with
    ``denominator_unknown`` rather than inventing a progress."""

    total_supply: Mapped[Decimal | None]

    pool: Mapped[str | None] = mapped_column(Text)
    """The launchpad at creation — ``pump``. PumpPortal streams other launchpads
    under the same method (``bonk`` observed live), and the T4.1 normalizer
    refuses to build a pump.fun model for them; this column is what makes that
    refusal auditable rather than invisible. The **destination** of a migration
    is ``migrated_pool``: two axes, two columns."""

    mayhem_enabled: Mapped[bool | None]
    """``NULL`` = unknown. Never ``false`` by default — see the module docstring."""

    mayhem_mode: Mapped[str | None] = mapped_column(Text)
    mayhem_state: Mapped[str | None] = mapped_column(Text)

    completed_at: Mapped[datetime | None]
    """First observation of the curve being finished (``complete = true``).
    Distinct from ``migrated_at`` by construction (T4-MEME-RADAR.md §3)."""

    migrated_at: Mapped[datetime | None]
    migrated_pool: Mapped[str | None] = mapped_column(Text)
    """``pump-amm`` for PumpSwap, as PumpPortal reports it."""

    first_seen_source: Mapped[str] = mapped_column(Text)
    """``pumpportal_ws`` | ``pumpfun_rest`` | ``solana_rpc`` — which producer put
    this row here. Not an enum: the set of producers is open in value and closed
    in shape, the same argument ``shadow_episodes.cohort`` makes (§16.3)."""

    first_seen_at: Mapped[datetime]
    """``observed_at`` of the first observation — always known, which is why
    retention keys on it and not on ``created_at``."""

    last_seen_at: Mapped[datetime]
    """The newest observation of this mint. Feeds the radar's staleness column."""

    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class MemeIngestGap(Base, UUIDPrimaryKeyMixin):
    """A window in which a meme stream was **not** listening. Append-only."""

    __tablename__ = "meme_ingest_gaps"
    __table_args__ = (
        Index("ix_meme_ingest_gaps_stream_gap_start", "stream", "gap_start"),
        CheckConstraint("gap_end > gap_start", name="a_gap_is_a_window"),
        CheckConstraint(
            "char_length(stream) > 0 AND char_length(reason) > 0",
            name="a_gap_names_its_stream_and_reason",
        ),
        CheckConstraint(
            "mint IS NULL OR char_length(mint) > 0",
            name="a_scoped_gap_names_a_mint",
        ),
        CheckConstraint("generation IS NULL OR generation >= 0", name="generation_is_not_negative"),
    )

    stream: Mapped[str] = mapped_column(Text)
    """``pumpportal_ws`` | ``curve_poll`` | ``features_1m``. Three different
    operator problems: the discovery feed dropped, the poll budget did not reach
    a mint, or a minute produced no feature row at all."""

    mint: Mapped[str | None] = mapped_column(Text)
    """``NULL`` = the whole stream was down, so naming one mint would understate
    it. Non-null = this mint was skipped while the stream was up."""

    gap_start: Mapped[datetime]
    gap_end: Mapped[datetime]
    detected_at: Mapped[datetime] = mapped_column(server_default=func.now())
    reason: Mapped[str] = mapped_column(Text)
    """``ws_disconnected`` | ``rate_limited`` | ``budget_exhausted`` |
    ``not_polled`` | ``process_restart`` — the same vocabulary the feature rows
    use for their reasons, so a null in a chart and a gap in the ledger can be
    read as the same event."""

    generation: Mapped[int | None] = mapped_column(Integer)
    """The WS connection generation (``ws.py``'s counter) the gap was detected
    across. A reconnection is what *proves* the gap; it is not a recovery."""

    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
