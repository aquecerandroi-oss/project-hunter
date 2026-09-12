"""``repositories/meme.py`` against a real Postgres (T4.3) — testcontainer.

Schema source: ``.claude/state/notes-T4.2.md`` §"contrato" (T4.2,
database-architect, migration ``0021_meme_radar``) — this file's DDL and seed
match the frozen contract published there, not a reconstruction (see
``repositories/meme_tables.py``'s module docstring for the same note).

Deliberately **not** wired through ``tests/integration/conftest.py``'s
``api_database_url`` (Alembic to head, shared ``hunter_api_it`` database):
depending on Alembic-to-head here would make this suite's pass/fail depend on
migration ``0021`` having actually landed there, which is exactly the kind of
flake this project's "never a background shell, one testcontainer at a time"
discipline exists to avoid. Instead: this file gets its own database inside
the shared, session-scoped ``postgres_container`` (``tests/conftest.py``) and
applies its own DDL — the same tables and view, spelled out once more here as
literal SQL rather than imported from ``repositories/meme_tables.py``, so a
typo in one is not hidden by copying it into the other.

Seed data: the primary mint/reserves/creator/bonding-curve values below are
copied from T4.1's live capture
(``packages/exchange-adapters/tests/fixtures/pumpfun/mayhem_list_raw.json``,
2026-09-12) and converted from raw lamports/token-subunits to the human units
T4.1's ``normalize.py`` already establishes as this project's convention
(SOL, tokens with 6 decimals) — never invented numbers. The additional mints
covering ``completed``/``migrated``/"never observed" states, and every
``meme_features_1m`` row (there is no producer for those in T4.1's capture),
are synthetic, labelled as such.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from hunter_api.repositories.meme import MemeRepository
from hunter_api.repositories.meme_cursor import decode_token_cursor, encode_token_cursor

if TYPE_CHECKING:
    from testcontainers.community.postgres import PostgresContainer

pytestmark = pytest.mark.integration

DB_NAME = "hunter_meme_it"

DDL_STATEMENTS = [
    """
    CREATE TABLE meme_tokens (
        mint text PRIMARY KEY,
        name text,
        symbol text,
        uri text,
        creator text,
        created_at timestamptz,
        bonding_curve text,
        initial_virtual_sol_reserves numeric(28, 10),
        initial_virtual_token_reserves numeric(28, 10),
        initial_real_token_reserves numeric(28, 10),
        total_supply numeric(28, 10),
        pool text,
        mayhem_enabled boolean,
        mayhem_mode text,
        mayhem_state text,
        completed_at timestamptz,
        migrated_at timestamptz,
        migrated_pool text,
        first_seen_source text NOT NULL,
        first_seen_at timestamptz NOT NULL,
        last_seen_at timestamptz NOT NULL,
        updated_at timestamptz NOT NULL,
        rest_complete_seen_at timestamptz,
        curve_filled_seen_at timestamptz,
        graduated_board_seen_at timestamptz,
        pool_created_at timestamptz,
        pool_created_source text,
        progress_denominator_source text
    )
    """,
    """
    CREATE TABLE meme_curve_snapshots (
        observed_at timestamptz NOT NULL,
        mint text NOT NULL,
        source text NOT NULL,
        received_at timestamptz NOT NULL,
        virtual_sol_reserves numeric(28, 10) NOT NULL,
        virtual_token_reserves numeric(28, 10) NOT NULL,
        real_sol_reserves numeric(28, 10) NOT NULL,
        real_token_reserves numeric(28, 10) NOT NULL,
        total_supply numeric(28, 10) NOT NULL,
        complete boolean NOT NULL,
        slot bigint,
        commitment text,
        mayhem_enabled boolean,
        mayhem_state text,
        mayhem_mode text,
        mcap_sol numeric(28, 10) GENERATED ALWAYS AS
            ((virtual_sol_reserves / NULLIF(virtual_token_reserves, 0)) * total_supply) STORED,
        PRIMARY KEY (observed_at, mint, source)
    )
    """,
    """
    CREATE TABLE meme_features_1m (
        end_time timestamptz NOT NULL,
        mint text NOT NULL,
        features_version text NOT NULL,
        curve_progress_pct numeric(9, 6),
        progress_reason text,
        mcap_sol numeric(28, 10),
        curve_reason text,
        unique_buyers integer,
        unique_buyers_reason text,
        buy_sell_ratio numeric(18, 8),
        buy_sell_ratio_reason text,
        top10_share numeric(9, 6),
        top10_share_reason text,
        creator_sold boolean,
        creator_sold_reason text,
        age_minutes integer,
        coverage numeric(9, 6) NOT NULL,
        snapshot_observed_at timestamptz,
        snapshot_source text,
        computed_at timestamptz NOT NULL,
        PRIMARY KEY (end_time, mint, features_version)
    )
    """,
    """
    CREATE TABLE meme_ingest_gaps (
        id uuid PRIMARY KEY,
        stream text NOT NULL,
        mint text,
        gap_start timestamptz NOT NULL,
        gap_end timestamptz NOT NULL,
        detected_at timestamptz NOT NULL,
        reason text,
        generation integer,
        detail jsonb
    )
    """,
    """
    CREATE VIEW meme_radar_features_v1 AS
    SELECT f.mint, f.end_time, f.features_version, f.curve_progress_pct, f.progress_reason,
           f.mcap_sol, f.curve_reason, f.unique_buyers, f.unique_buyers_reason, f.buy_sell_ratio,
           f.buy_sell_ratio_reason, f.top10_share, f.top10_share_reason, f.creator_sold,
           f.creator_sold_reason, f.age_minutes, f.coverage, f.snapshot_observed_at,
           f.snapshot_source, t.name, t.symbol, t.creator, t.created_at AS token_created_at,
           t.pool, t.mayhem_enabled, t.mayhem_mode, t.mayhem_state, t.completed_at,
           t.migrated_at, t.migrated_pool, t.first_seen_source, t.last_seen_at,
           t.rest_complete_seen_at, t.curve_filled_seen_at, t.graduated_board_seen_at,
           t.pool_created_at, t.pool_created_source, t.progress_denominator_source
    FROM meme_features_1m f JOIN meme_tokens t ON t.mint = f.mint
    """,
    # T4.2d: the matrix view the overview reads (``0024``); empty here, its shape only.
    """
    CREATE VIEW meme_graduation_matrix_v1 AS
    SELECT CAST(NULL AS date) AS day_brt, 0::bigint AS mints, 0::bigint AS completed,
           0::bigint AS rest_complete, 0::bigint AS curve_filled, 0::bigint AS graduated_board,
           0::bigint AS pool_created, 0::bigint AS signals_1, 0::bigint AS signals_2,
           0::bigint AS signals_3, 0::bigint AS signals_4, 0::bigint AS disagree_rest_filled,
           0::bigint AS disagree_rest_board, 0::bigint AS disagree_rest_pool,
           0::bigint AS disagree_filled_board, 0::bigint AS disagree_filled_pool,
           0::bigint AS disagree_board_pool, 0::bigint AS rest_only_unclassified
    WHERE false
    """,
]

# T4.1 fixture (mayhem_list_raw.json): one real token, mid-curve, not completed.
MINT_CURVE = "Fh42kAfy27CGoUA8CgFwpTGMubzndaAyTy2gghu5pump"
# Synthetic (labelled): covers `completed_at` set, `migrated_at` unset.
MINT_COMPLETED = "Synthetic1CompletedNotMigratedxxxxxxxxxxxxx"
# Synthetic (labelled): covers `migrated_at` set.
MINT_MIGRATED = "Synthetic2MigratedToPumpSwapxxxxxxxxxxxxxxx"
# Synthetic (labelled): covers neither timestamp ever observed.
MINT_UNKNOWN = "Synthetic3NeverObservedCompletionxxxxxxxxxxx"
# Synthetic (labelled): in `meme_tokens` but with no `meme_features_1m` row at
# all -- must never appear in `list_tokens` (contract §6/§7).
MINT_NO_FEATURES = "Synthetic4NoFeaturesRowYetxxxxxxxxxxxxxxxxxx"
# Synthetic (labelled): a migration event reached this radar before the
# token's own creation event did (contract §1, a documented T4.1 scenario) --
# `created_at IS NULL`.
MINT_NO_CREATION = "Synthetic5MigrationBeforeCreationxxxxxxxxxxx"

T0 = datetime(2026, 9, 12, 1, 30, 41, tzinfo=UTC)


async def _create_database(admin_url: str) -> str:
    engine = create_async_engine(
        admin_url, isolation_level="AUTOCOMMIT", connect_args={"statement_cache_size": 0}
    )
    try:
        async with engine.connect() as connection:
            exists = await connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": DB_NAME}
            )
            if not exists:
                await connection.execute(text(f'CREATE DATABASE "{DB_NAME}"'))
    finally:
        await engine.dispose()
    return admin_url.rsplit("/", 1)[0] + "/" + DB_NAME


async def _setup_schema(url: str) -> None:
    """DDL + seed, run once inside its own throwaway event loop
    (``asyncio.run``, module-scoped fixture below) — never shared with a
    test's own loop. asyncpg's connection/lock objects are bound to the loop
    that created them; reusing an engine across pytest-asyncio's per-test
    loops corrupts the protocol state ("another operation is in progress"),
    which is exactly why :func:`session` below opens and disposes its own
    engine per test instead of reusing one built here."""
    engine = create_async_engine(url, connect_args={"statement_cache_size": 0})
    try:
        async with engine.begin() as connection:
            for statement in DDL_STATEMENTS:
                await connection.execute(text(statement))
            await _seed(connection)
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def meme_database_url(postgres_container: PostgresContainer) -> str:
    url = asyncio.run(_create_database(postgres_container.get_connection_url()))
    asyncio.run(_setup_schema(url))
    return url


def _token_row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "mint": None,
        "name": None,
        "symbol": None,
        "uri": None,
        "creator": None,
        "created_at": None,
        "bonding_curve": None,
        "ivsr": None,
        "ivtr": None,
        "irtr": None,
        "total_supply": None,
        "pool": "pump",
        "mayhem_enabled": None,
        "mayhem_mode": None,
        "mayhem_state": None,
        "completed_at": None,
        "migrated_at": None,
        "migrated_pool": None,
        "first_seen_source": "pumpportal_ws",
        "first_seen_at": T0,
        "last_seen_at": T0,
    }
    base.update(overrides)
    base["updated_at"] = base["last_seen_at"]
    return base


async def _seed(connection: object) -> None:
    execute = connection.execute  # type: ignore[attr-defined]
    await execute(
        text(
            """
            INSERT INTO meme_tokens (
                mint, name, symbol, uri, creator, created_at, bonding_curve,
                initial_virtual_sol_reserves, initial_virtual_token_reserves,
                initial_real_token_reserves, total_supply, pool, mayhem_enabled,
                mayhem_mode, mayhem_state, completed_at, migrated_at, migrated_pool,
                first_seen_source, first_seen_at, last_seen_at, updated_at
            ) VALUES (
                :mint, :name, :symbol, :uri, :creator, :created_at, :bonding_curve,
                :ivsr, :ivtr, :irtr, :total_supply, :pool, :mayhem_enabled, :mayhem_mode,
                :mayhem_state, :completed_at, :migrated_at, :migrated_pool,
                :first_seen_source, :first_seen_at, :last_seen_at, :updated_at
            )
            """
        ),
        [
            _token_row(
                mint=MINT_CURVE,
                name="bum bum",
                symbol="bam bum",
                uri="https://ipfs.io/ipfs/QmZ6byFRSQncuuE16aa7nwAEeG7DUMoWRfu591u7ZfFB2z",
                creator="s9uu4shkYUQUmnWN2jkwgA2Nbg2Rmv7vUprtjy71xgP",
                created_at=T0,
                bonding_curve="7Y529vXmLZRqX2if1E4CA1aYtRgoVRySmo9rJwjoYWDo",
                ivsr=Decimal("30"),
                ivtr=Decimal("1073000000"),
                irtr=Decimal("793100000"),
                total_supply=Decimal("1000000000"),
                mayhem_enabled=True,
                mayhem_mode="auto",
                mayhem_state="active",
                last_seen_at=T0 + timedelta(minutes=5),
            ),
            _token_row(
                mint=MINT_COMPLETED,
                name="Synthetic Completed",
                symbol="SYNC1",
                creator="SyntheticCreator1xxxxxxxxxxxxxxxxxxxxxxxxxxx",
                created_at=T0 - timedelta(hours=2),
                bonding_curve="SyntheticCurve1",
                ivsr=Decimal("30"),
                ivtr=Decimal("1073000000"),
                irtr=Decimal("793100000"),
                total_supply=Decimal("1000000000"),
                mayhem_enabled=False,
                mayhem_mode="unknown",
                completed_at=T0 - timedelta(hours=1),
                last_seen_at=T0 - timedelta(hours=1),
            ),
            _token_row(
                mint=MINT_MIGRATED,
                name="Synthetic Migrated",
                symbol="SYNC2",
                creator="SyntheticCreator2xxxxxxxxxxxxxxxxxxxxxxxxxxx",
                created_at=T0 - timedelta(days=1),
                bonding_curve="SyntheticCurve2",
                ivsr=Decimal("30"),
                ivtr=Decimal("1073000000"),
                irtr=Decimal("793100000"),
                total_supply=Decimal("1000000000"),
                mayhem_enabled=False,
                mayhem_mode="unknown",
                completed_at=T0 - timedelta(days=1) + timedelta(hours=6),
                migrated_at=T0 - timedelta(hours=3),
                migrated_pool="SyntheticPumpSwapPool2",
                last_seen_at=T0 - timedelta(hours=3),
            ),
            _token_row(
                mint=MINT_UNKNOWN,
                name="Synthetic Unknown Completion",
                symbol="SYNC3",
                creator="SyntheticCreator3xxxxxxxxxxxxxxxxxxxxxxxxxxx",
                created_at=T0 - timedelta(minutes=2),
                bonding_curve="SyntheticCurve3",
                ivsr=Decimal("30"),
                ivtr=Decimal("1073000000"),
                irtr=Decimal("793100000"),
                total_supply=Decimal("1000000000"),
                last_seen_at=T0 - timedelta(minutes=2),
            ),
            _token_row(
                mint=MINT_NO_FEATURES,
                name="Synthetic No Features Row",
                symbol="SYNC4",
                creator="SyntheticCreator4xxxxxxxxxxxxxxxxxxxxxxxxxxx",
                created_at=T0 - timedelta(minutes=1),
                bonding_curve="SyntheticCurve4",
                last_seen_at=T0 - timedelta(minutes=1),
            ),
            _token_row(
                mint=MINT_NO_CREATION,
                name=None,
                symbol=None,
                creator=None,
                created_at=None,
                first_seen_source="pumpportal_ws",
                last_seen_at=T0,
            ),
        ],
    )
    await execute(
        text(
            """
            INSERT INTO meme_curve_snapshots (
                observed_at, mint, source, received_at, virtual_sol_reserves,
                virtual_token_reserves, real_sol_reserves, real_token_reserves,
                total_supply, complete
            ) VALUES (:observed_at, :mint, :source, :observed_at, :vsr, :vtr, :rsr, :rtr, :total_supply, :complete)
            """
        ),
        [
            {
                "observed_at": T0,
                "mint": MINT_CURVE,
                "source": "pumpfun_rest",
                "vsr": Decimal("9.713447588"),
                "vtr": Decimal("1072520031.280431"),
                "rsr": Decimal("0.019167922"),
                "rtr": Decimal("792620031.280431"),
                "total_supply": Decimal("1000000000"),
                "complete": False,
            },
            {
                "observed_at": T0 + timedelta(minutes=5),
                "mint": MINT_CURVE,
                "source": "solana_rpc",
                "vsr": Decimal("9.8"),
                "vtr": Decimal("1071000000"),
                "rsr": Decimal("0.12"),
                "rtr": Decimal("791100000"),
                "total_supply": Decimal("1000000000"),
                "complete": False,
            },
            {
                "observed_at": T0 - timedelta(hours=3),
                "mint": MINT_MIGRATED,
                "source": "pumpfun_rest",
                "vsr": Decimal("120"),
                "vtr": Decimal("400000000"),
                "rsr": Decimal("90"),
                "rtr": Decimal("0"),
                "total_supply": Decimal("1000000000"),
                "complete": True,
            },
        ],
    )
    # meme_features_1m: no producer in T4.1's real capture -- every row here
    # is synthetic, built to exercise the null-with-reason contract and the
    # "latest closed minute" list query. All four tracked mints (not
    # MINT_NO_FEATURES) get an `end_time = T0 + 1min` row so `list_tokens`'s
    # "latest minute" page has one candidate per state.
    last_minute = T0 + timedelta(minutes=1)
    await execute(
        text(
            """
            INSERT INTO meme_features_1m (
                end_time, mint, features_version, curve_progress_pct, progress_reason,
                mcap_sol, curve_reason, unique_buyers, unique_buyers_reason, buy_sell_ratio,
                buy_sell_ratio_reason, top10_share, top10_share_reason, creator_sold,
                creator_sold_reason, age_minutes, coverage, snapshot_observed_at,
                snapshot_source, computed_at
            ) VALUES (
                :end_time, :mint, 'meme_features_v1', :progress, :progress_reason, :mcap,
                :curve_reason, :buyers, :buyers_reason, :ratio, :ratio_reason, :top10,
                :top10_reason, :creator_sold, :creator_sold_reason, :age, :coverage,
                :snap_observed_at, :snap_source, :end_time
            )
            """
        ),
        [
            {
                "end_time": T0,
                "mint": MINT_CURVE,
                "progress": Decimal("0.000605"),
                "progress_reason": None,
                "mcap": Decimal("9.06"),
                "curve_reason": None,
                "buyers": None,
                "buyers_reason": "no_trade_feed",
                "ratio": None,
                "ratio_reason": "no_trade_feed",
                "top10": None,
                "top10_reason": "no_holders_reader",
                "creator_sold": None,
                "creator_sold_reason": "no_holders_reader",
                "age": 0,
                "coverage": Decimal("1"),
                "snap_observed_at": T0,
                "snap_source": "pumpfun_rest",
            },
            {
                "end_time": last_minute,
                "mint": MINT_CURVE,
                "progress": Decimal("0.00189"),
                "progress_reason": None,
                "mcap": Decimal("9.14"),
                "curve_reason": None,
                "buyers": None,
                "buyers_reason": "no_trade_feed",
                "ratio": None,
                "ratio_reason": "no_trade_feed",
                "top10": None,
                "top10_reason": "no_holders_reader",
                "creator_sold": None,
                "creator_sold_reason": "no_holders_reader",
                "age": 1,
                "coverage": Decimal("1"),
                "snap_observed_at": T0 + timedelta(minutes=5),
                "snap_source": "solana_rpc",
            },
            {
                "end_time": last_minute,
                "mint": MINT_COMPLETED,
                "progress": Decimal("1"),
                "progress_reason": None,
                "mcap": Decimal("0.5"),
                "curve_reason": None,
                "buyers": None,
                "buyers_reason": "no_trade_feed",
                "ratio": None,
                "ratio_reason": "no_trade_feed",
                "top10": None,
                "top10_reason": "no_holders_reader",
                "creator_sold": None,
                "creator_sold_reason": "no_holders_reader",
                "age": 120,
                "coverage": Decimal("1"),
                "snap_observed_at": T0 - timedelta(hours=1),
                "snap_source": "pumpfun_rest",
            },
            {
                "end_time": last_minute,
                "mint": MINT_MIGRATED,
                "progress": Decimal("1"),
                "progress_reason": None,
                "mcap": Decimal("300"),
                "curve_reason": None,
                "buyers": None,
                "buyers_reason": "no_trade_feed",
                "ratio": None,
                "ratio_reason": "no_trade_feed",
                "top10": None,
                "top10_reason": "no_holders_reader",
                "creator_sold": None,
                "creator_sold_reason": "no_holders_reader",
                "age": 1440,
                "coverage": Decimal("1"),
                "snap_observed_at": T0 - timedelta(hours=3),
                "snap_source": "pumpfun_rest",
            },
            {
                "end_time": last_minute,
                "mint": MINT_UNKNOWN,
                "progress": None,
                "progress_reason": "denominator_unknown",
                "mcap": None,
                "curve_reason": "not_polled",
                "buyers": None,
                "buyers_reason": "no_trade_feed",
                "ratio": None,
                "ratio_reason": "no_trade_feed",
                "top10": None,
                "top10_reason": "no_holders_reader",
                "creator_sold": None,
                "creator_sold_reason": "no_holders_reader",
                "age": 3,
                "coverage": Decimal("0.5"),
                "snap_observed_at": None,
                "snap_source": None,
            },
        ],
    )
    await execute(
        text(
            """
            INSERT INTO meme_ingest_gaps (id, stream, mint, gap_start, gap_end, detected_at, reason, generation, detail)
            VALUES (:id, :stream, :mint, :gap_start, :gap_end, :detected_at, :reason, :generation, :detail)
            """
        ),
        [
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "meme-gap-1")),
                "stream": "pumpportal_ws",
                "mint": None,
                "gap_start": T0 - timedelta(minutes=30),
                "gap_end": T0 - timedelta(minutes=28),
                "detected_at": T0 - timedelta(minutes=28),
                "reason": "reconnect_backoff",
                "generation": 3,
                "detail": '{"attempts": 2}',
            },
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "meme-gap-2")),
                "stream": "curve_poll",
                "mint": MINT_CURVE,
                "gap_start": T0 - timedelta(minutes=10),
                "gap_end": T0 - timedelta(minutes=9),
                "detected_at": T0 - timedelta(minutes=9),
                "reason": "rate_limited",
                "generation": None,
                "detail": None,
            },
        ],
    )


@pytest_asyncio.fixture
async def session(meme_database_url: str) -> AsyncIterator[AsyncSession]:
    """A fresh engine per test function -- see :func:`_setup_schema` for why
    an engine (and the asyncpg connections/locks it owns) must never outlive
    the single pytest-asyncio event loop it was created under."""
    engine = create_async_engine(meme_database_url, connect_args={"statement_cache_size": 0})
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as s:
            yield s
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def repo(session: AsyncSession) -> MemeRepository:
    return MemeRepository(session)


class TestOverviewAggregates:
    async def test_coverage_count(self, repo: MemeRepository) -> None:
        assert await repo.token_coverage_count() == 6

    async def test_mayhem_active_count(self, repo: MemeRepository) -> None:
        assert await repo.mayhem_active_count() == 1

    async def test_graduations_last_24h(self, repo: MemeRepository) -> None:
        now = T0 + timedelta(hours=1)
        assert await repo.graduations_last_24h(now) == 1

    async def test_created_counts_exclude_null_created_at(self, repo: MemeRepository) -> None:
        """``MINT_NO_CREATION`` has ``created_at IS NULL`` (contract §1: a
        migration event reached this radar before the creation event did) --
        it must be silently excluded from both windows, never counted as
        "just created" nor as an error."""
        now = T0 + timedelta(minutes=10)
        last_24h, last_7d = await repo.created_counts_by_window(now)
        # MINT_MIGRATED was "created" exactly 24h before T0 -- outside the
        # 24h window measured from `now` (10 min after T0), inside the 7d one.
        assert last_24h == 4  # CURVE, COMPLETED, UNKNOWN, NO_FEATURES
        assert last_7d == 5  # + MIGRATED; MINT_NO_CREATION (created_at NULL) excluded from both


class TestListTokensState:
    async def test_state_curve_excludes_completed_and_migrated(self, repo: MemeRepository) -> None:
        rows = await repo.list_tokens(state="curve", sort="mcap", limit=50, cursor=None)
        assert {r.mint for r in rows} == {MINT_CURVE, MINT_UNKNOWN}

    async def test_state_completed_excludes_migrated(self, repo: MemeRepository) -> None:
        rows = await repo.list_tokens(state="completed", sort="mcap", limit=50, cursor=None)
        assert {r.mint for r in rows} == {MINT_COMPLETED}

    async def test_state_migrated(self, repo: MemeRepository) -> None:
        rows = await repo.list_tokens(state="migrated", sort="mcap", limit=50, cursor=None)
        assert {r.mint for r in rows} == {MINT_MIGRATED}

    async def test_no_features_row_never_appears(self, repo: MemeRepository) -> None:
        """Contract §6/§7: the radar list is driven by ``meme_features_1m``
        via the view -- a token with no feature row at all is simply absent
        from every state's page, never shown with fabricated nulls."""
        rows = await repo.list_tokens(state=None, sort="mcap", limit=50, cursor=None)
        assert MINT_NO_FEATURES not in {r.mint for r in rows}


class TestListTokensSortAndPagination:
    async def test_sort_by_mcap_desc(self, repo: MemeRepository) -> None:
        rows = await repo.list_tokens(state=None, sort="mcap", limit=50, cursor=None)
        mcaps = [r.mcap_sol for r in rows if r.mcap_sol is not None]
        assert mcaps == sorted(mcaps, reverse=True)
        # MINT_UNKNOWN's mcap is null (curve_reason="not_polled") -- it must
        # still appear (state=None) but sort last, never as if mcap were 0.
        assert rows[-1].mint == MINT_UNKNOWN
        assert rows[-1].mcap_sol is None

    async def test_pagination_covers_every_row_once(self, repo: MemeRepository) -> None:
        seen: list[str] = []
        cursor = None
        for _ in range(10):
            rows = await repo.list_tokens(state=None, sort="mcap", limit=2, cursor=cursor)
            if not rows:
                break
            seen.extend(r.mint for r in rows)
            last = rows[-1]
            cursor = decode_token_cursor(encode_token_cursor("mcap", last.mcap_sol, last.mint))
        assert sorted(seen) == sorted([MINT_CURVE, MINT_COMPLETED, MINT_MIGRATED, MINT_UNKNOWN])
        assert len(seen) == len(set(seen))


class TestGetTokenDetail:
    async def test_get_token_returns_latest_snapshot(self, repo: MemeRepository) -> None:
        row = await repo.get_token(MINT_CURVE)
        assert row is not None
        assert row.snapshot_source == "solana_rpc"  # the later of the two feature rows
        assert row.snapshot_observed_at == T0 + timedelta(minutes=5)

    async def test_get_token_missing_returns_none(self, repo: MemeRepository) -> None:
        assert await repo.get_token("NoSuchMintxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx") is None

    async def test_get_token_with_no_features_row_falls_back_to_identity(
        self, repo: MemeRepository
    ) -> None:
        """No ``meme_features_1m`` row exists for this mint -- the detail
        endpoint still resolves the token's identity from ``meme_tokens``
        alone, with every curve field an honest ``None``."""
        row = await repo.get_token(MINT_NO_FEATURES)
        assert row is not None
        assert row.name == "Synthetic No Features Row"
        assert row.snapshot_observed_at is None
        assert row.snapshot_source is None
        assert row.mcap_sol is None

    async def test_list_snapshots_newest_first(self, repo: MemeRepository) -> None:
        rows = await repo.list_snapshots(MINT_CURVE, limit=10)
        assert len(rows) == 2
        assert rows[0].observed_at > rows[1].observed_at

    async def test_snapshot_mcap_is_generated_column(self, repo: MemeRepository) -> None:
        rows = await repo.list_snapshots(MINT_CURVE, limit=10)
        newest = rows[0]
        expected = (newest.virtual_sol_reserves / newest.virtual_token_reserves) * Decimal(
            "1000000000"
        )
        assert newest.mcap_sol is not None
        assert abs(newest.mcap_sol - expected) < Decimal("0.0001")

    async def test_list_features_carries_null_reasons(self, repo: MemeRepository) -> None:
        rows = await repo.list_features(MINT_UNKNOWN, limit=10)
        assert len(rows) == 1
        row = rows[0]
        assert row.mcap_sol is None
        assert row.curve_reason == "not_polled"
        assert row.curve_progress_pct is None
        assert row.progress_reason == "denominator_unknown"


class TestGaps:
    async def test_list_gaps_newest_first(self, repo: MemeRepository) -> None:
        rows = await repo.list_gaps(limit=10, cursor=None)
        assert len(rows) == 2
        assert rows[0].detected_at >= rows[1].detected_at

    async def test_list_gaps_feed_wide_has_no_mint(self, repo: MemeRepository) -> None:
        rows = await repo.list_gaps(limit=10, cursor=None)
        feed_wide = [r for r in rows if r.mint is None]
        assert len(feed_wide) == 1
        assert feed_wide[0].stream == "pumpportal_ws"
        assert feed_wide[0].generation == 3
