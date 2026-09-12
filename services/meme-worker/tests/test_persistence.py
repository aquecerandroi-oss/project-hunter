"""The persistence path against a real Postgres — one file, one container.

Everything proved here only exists in a database: the upsert that fills a hole and
never blanks a value, the write-once trigger behind it, the monthly partition a row
routes to, the generated market cap, the biconditional CHECKs on the reason columns,
and the marker retention has to declare. A fake session would compile the
statements and prove none of it.

Every write runs as ``hunter_worker`` through ``role_session``, which is the §27.5
finding not repeated: the scanner has transactions with no ``SET LOCAL ROLE`` that
work only because the login happens to own the schema.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from hunter_meme_worker.features import (
    NO_HOLDERS_READER,
    NO_TRADE_FEED,
    NOT_POLLED,
    CurveObservation,
    MinuteInputs,
    build_row,
)
from hunter_meme_worker.repo import (
    GapRow,
    SnapshotRow,
    TokenRow,
    insert_features,
    insert_snapshot,
    load_tracked,
    prune_tokens,
    record_gap,
    upsert_token,
)
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from hunter_core.db.session import role_session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

WORKER = "hunter_worker"
APP = "hunter_app"
OCTOBER = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
NOVEMBER = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


def _token(mint: str, *, seen: datetime, **kw: object) -> TokenRow:
    defaults: dict[str, object] = {
        "mint": mint,
        "first_seen_source": "pumpportal_ws",
        "first_seen_at": seen,
        "last_seen_at": seen,
    }
    defaults.update(kw)
    return TokenRow(**defaults)  # type: ignore[arg-type]


def _snapshot(mint: str, *, observed_at: datetime, source: str = "pumpfun_rest") -> SnapshotRow:
    return SnapshotRow(
        observed_at=observed_at,
        mint=mint,
        source=source,
        virtual_sol_reserves=Decimal(30),
        virtual_token_reserves=Decimal(1_073_000_000),
        real_sol_reserves=Decimal(0),
        real_token_reserves=Decimal(793_100_000),
        total_supply=Decimal(1_000_000_000),
        complete=False,
    )


async def test_the_upsert_fills_a_hole_and_never_blanks_a_known_value(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Idempotent by SQL, not by a prior read — and write-once by trigger."""
    mint = "UPSERT_MINT"
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await upsert_token(
            session,
            _token(mint, seen=OCTOBER, name="Original", symbol="ORI", created_at=OCTOBER),
        )
    # A migration frame for the same mint: no name, no symbol, no creation time.
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await upsert_token(
            session,
            _token(
                mint,
                seen=OCTOBER + timedelta(minutes=5),
                first_seen_source="pumpfun_rest",
                migrated_at=OCTOBER + timedelta(minutes=5),
                migrated_pool="pump-amm",
            ),
        )
    async with role_session(db_session_factory, db_role=WORKER) as session:
        row = (
            (
                await session.execute(
                    text(
                        "SELECT name, symbol, created_at, first_seen_source, first_seen_at, "
                        "last_seen_at, migrated_at, migrated_pool, count(*) OVER () AS rows "
                        "FROM meme_tokens WHERE mint = :mint"
                    ),
                    {"mint": mint},
                )
            )
            .mappings()
            .one()
        )
    assert row["rows"] == 1, "the upsert wrote a second row for the same mint"
    assert row["name"] == "Original" and row["symbol"] == "ORI"
    assert row["created_at"] == OCTOBER
    assert row["first_seen_source"] == "pumpportal_ws", "provenance of the first sighting moved"
    assert row["first_seen_at"] == OCTOBER
    assert row["last_seen_at"] == OCTOBER + timedelta(minutes=5), "last_seen_at did not advance"
    assert row["migrated_pool"] == "pump-amm"


async def test_a_migration_first_row_is_legal_and_a_creation_fills_it_once(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The mandatory T4.1 scenario: the curve may predate the collector."""
    mint = "MIGRATION_FIRST"
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await upsert_token(
            session,
            _token(mint, seen=OCTOBER, migrated_at=OCTOBER, migrated_pool="pump-amm"),
        )
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await upsert_token(
            session, _token(mint, seen=OCTOBER, name="Late", created_at=OCTOBER, pool="pump")
        )
        name = await session.scalar(
            text("SELECT name FROM meme_tokens WHERE mint = :mint"), {"mint": mint}
        )
    assert name == "Late", "an identity that arrived late was refused instead of filled"


async def test_rewriting_a_known_identity_is_refused_for_the_worker(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mint = "FROZEN_IDENTITY"
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await upsert_token(session, _token(mint, seen=OCTOBER, name="First"))
    with pytest.raises(DBAPIError, match="written once"):
        async with role_session(db_session_factory, db_role=WORKER) as session:
            await session.execute(
                text("UPDATE meme_tokens SET name = 'Renamed' WHERE mint = :mint"), {"mint": mint}
            )
    async with role_session(db_session_factory, db_role=WORKER) as session:
        # The lifecycle still moves: that is the whole reason UPDATE is granted.
        await session.execute(
            text("UPDATE meme_tokens SET mayhem_state = 'active' WHERE mint = :mint"),
            {"mint": mint},
        )
        state = await session.scalar(
            text("SELECT mayhem_state FROM meme_tokens WHERE mint = :mint"), {"mint": mint}
        )
    assert state == "active"


async def test_a_snapshot_is_idempotent_and_routes_to_its_month(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mint = "SNAPSHOT_MINT"
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_snapshot(session, _snapshot(mint, observed_at=OCTOBER))
        await insert_snapshot(session, _snapshot(mint, observed_at=OCTOBER))
        await insert_snapshot(session, _snapshot(mint, observed_at=NOVEMBER))
        # The same instant from the *other* source is a second observation, not a
        # duplicate: reconciling them is the point (source is in the key).
        await insert_snapshot(session, _snapshot(mint, observed_at=OCTOBER, source="solana_rpc"))
    async with role_session(db_session_factory, db_role=WORKER) as session:
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT observed_at, source, mcap_sol, tableoid::regclass::text AS part "
                        "FROM meme_curve_snapshots WHERE mint = :mint ORDER BY observed_at, source"
                    ),
                    {"mint": mint},
                )
            )
            .mappings()
            .all()
        )
    assert len(rows) == 3, "the re-read of one instant from one source was not deduplicated"
    assert rows[0]["part"] == "meme_curve_snapshots_2026_10"
    assert rows[2]["part"] == "meme_curve_snapshots_2026_11"
    expected = (Decimal(30) / Decimal(1_073_000_000)) * Decimal(1_000_000_000)
    assert rows[0]["mcap_sol"] == expected.quantize(Decimal("0.0000000001")), (
        "the generated market cap is not marginal price x supply"
    )


async def test_a_folded_minute_round_trips_and_routes_to_its_month(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The fold, the CHECKs and the partition, through the real ``build_row``."""
    mint = "FEATURES_MINT"
    observation = CurveObservation(
        observed_at=OCTOBER,
        source="pumpfun_rest",
        real_token_reserves=Decimal("396550000"),
        mcap_sol=Decimal("27.9589934762"),
        complete=False,
    )
    covered = build_row(
        MinuteInputs(
            mint=mint,
            end_time=OCTOBER,
            created_at=OCTOBER - timedelta(minutes=9),
            initial_real_token_reserves=Decimal("793100000"),
            snapshot=observation,
        )
    )
    uncovered = build_row(
        MinuteInputs(
            mint=mint,
            end_time=NOVEMBER,
            created_at=None,
            initial_real_token_reserves=None,
            snapshot=None,
            absence_reason=NOT_POLLED,
        )
    )
    async with role_session(db_session_factory, db_role=WORKER) as session:
        assert await insert_features(session, [covered, uncovered]) == 2
        await insert_features(session, [covered])  # a re-fold writes nothing new

    async with role_session(db_session_factory, db_role=WORKER) as session:
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT end_time, curve_progress_pct, progress_reason, mcap_sol, curve_reason, "
                        "unique_buyers_reason, top10_share_reason, age_minutes, coverage, "
                        "snapshot_source, tableoid::regclass::text AS part "
                        "FROM meme_features_1m WHERE mint = :mint ORDER BY end_time"
                    ),
                    {"mint": mint},
                )
            )
            .mappings()
            .all()
        )
    assert len(rows) == 2, "the same minute was folded twice into two rows"
    first, second = rows
    assert first["part"] == "meme_features_1m_2026_10"
    assert second["part"] == "meme_features_1m_2026_11"
    assert first["curve_progress_pct"] == Decimal("0.500000")
    assert first["progress_reason"] is None and first["curve_reason"] is None
    assert first["age_minutes"] == 9 and first["coverage"] == Decimal(1)
    assert first["snapshot_source"] == "pumpfun_rest"
    assert first["unique_buyers_reason"] == NO_TRADE_FEED
    assert first["top10_share_reason"] == NO_HOLDERS_READER
    assert second["coverage"] == Decimal(0) and second["curve_reason"] == NOT_POLLED
    assert second["age_minutes"] is None, "an unknown creation time produced an age"


async def test_a_feature_value_without_a_reason_is_refused_by_the_database(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """MUST-FIX 1 as a constraint: an absence with no reason cannot be stored."""
    with pytest.raises(DBAPIError, match="is_null_with_a_reason"):
        async with role_session(db_session_factory, db_role=WORKER) as session:
            await session.execute(
                text(
                    "INSERT INTO meme_features_1m (end_time, mint, features_version, coverage) "
                    "VALUES (:t, 'NO_REASON', 'meme_features_v1', 1)"
                ),
                {"t": OCTOBER},
            )


async def test_a_gap_is_written_as_a_window_and_read_back(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await record_gap(
            session,
            GapRow(
                stream="pumpportal_ws",
                gap_start=OCTOBER,
                gap_end=OCTOBER + timedelta(seconds=30),
                reason="ws_disconnected",
                generation=3,
                detail={"previous_generation": 2},
            ),
        )
    async with role_session(db_session_factory, db_role=WORKER) as session:
        row = (
            (
                await session.execute(
                    text(
                        "SELECT stream, mint, reason, generation, detail FROM meme_ingest_gaps "
                        "WHERE stream = 'pumpportal_ws' ORDER BY detected_at DESC LIMIT 1"
                    )
                )
            )
            .mappings()
            .one()
        )
    assert row["mint"] is None, "a whole-stream gap must not name one mint"
    assert row["reason"] == "ws_disconnected"
    assert row["detail"] == {"previous_generation": 2}


async def test_retention_prunes_only_what_aged_out_and_needs_the_marker(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    old, young = "OLD_MINT", "YOUNG_MINT"
    cutoff = datetime(2026, 10, 1, tzinfo=UTC)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await upsert_token(session, _token(old, seen=cutoff - timedelta(days=10)))
        await upsert_token(session, _token(young, seen=cutoff + timedelta(days=10)))

    with pytest.raises(DBAPIError, match="declaring retention"):
        async with role_session(db_session_factory, db_role=WORKER) as session:
            await session.execute(text("DELETE FROM meme_tokens WHERE mint = :mint"), {"mint": old})

    async with role_session(db_session_factory, db_role=WORKER) as session:
        deleted = await prune_tokens(session, cutoff=cutoff, batch=100)
    assert deleted >= 1
    async with role_session(db_session_factory, db_role=WORKER) as session:
        survivors = set(
            (await session.execute(text("SELECT mint FROM meme_tokens"))).scalars().all()
        )
    assert old not in survivors and young in survivors


async def test_the_tracked_set_is_rebuilt_from_the_rows_a_restart_left_behind(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The durable checkpoint: a restart resumes the universe, it does not reset it.

    Since T4.2c a migrated curve whose completion was never *read* comes back
    for exactly one final poll (``final_read_pending``) — the fix for the hour
    with zero ``complete = true`` snapshots; a curve whose ``completed_at`` was
    observed stays out, because its reserves are static."""
    now = datetime(2026, 12, 1, 12, 0, tzinfo=UTC)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await upsert_token(
            session, _token("WARM_YOUNG", seen=now - timedelta(minutes=5), created_at=now)
        )
        await upsert_token(
            session,
            _token(
                "WARM_MIGRATED",
                seen=now,
                created_at=now,
                migrated_at=now,
                migrated_pool="pump-amm",
            ),
        )
        await upsert_token(
            session, _token("WARM_COMPLETED", seen=now, created_at=now, completed_at=now)
        )
    async with role_session(db_session_factory, db_role=WORKER) as session:
        tracked = {
            t.mint: t for t in await load_tracked(session, cutoff=now - timedelta(hours=24), cap=50)
        }
    assert "WARM_YOUNG" in tracked
    assert "WARM_COMPLETED" not in tracked, "an observed completion kept costing poll budget"
    assert tracked["WARM_MIGRATED"].final_read_pending, (
        "a migrated curve never read as complete must come back for its final read"
    )


async def test_the_api_role_reads_the_view_and_writes_none_of_it(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Proved as the role, not asked of the catalogue (§18.7's rule)."""
    async with role_session(db_session_factory, db_role=APP) as session:
        rows = await session.execute(
            text("SELECT mint, curve_reason, symbol FROM meme_radar_features_v1 LIMIT 5")
        )
        assert rows.mappings().all() is not None
    with pytest.raises((ProgrammingError, DBAPIError), match="permission denied"):
        async with role_session(db_session_factory, db_role=APP) as session:
            await session.execute(
                text(
                    "INSERT INTO meme_tokens (mint, first_seen_source, first_seen_at, last_seen_at) "
                    "VALUES ('APP_WRITE', 'pumpfun_rest', now(), now())"
                )
            )
