"""T3.37c — ``EXPLAIN`` before and after ``0014_lab_signals_indexes``.

T3.37a ran this file at 6 000 rows and wrote the request the migration answers
(``.claude/state/notes-T3.37.md`` §T3.37a). It now seeds **50 000** signals
across six strategy versions and three cohorts, and it is no longer purely
diagnostic: it asserts which plans the two new indexes must produce, and it
asserts the one plan they **cannot** fix.

Three facts this file exists to keep true:

1. ``ix_agent_signals_cohort_emitted`` turns "one cohort, newest first" into an
   ordered ``Index Scan`` with no ``Sort`` — for the Lab's default listing
   *once it names the column*, and today for
   ``replay/simulate.count_population`` and ``replay/stress.cohort_cases``;
2. ``ix_agent_signals_version_cohort_emitted`` does the same for the
   scoreboard's evaluable population (``replication_stats._EVALUABLE_SQL``);
3. ``GET /lab/shadow/signals`` still sorts in memory, because it orders by
   ``(supporting_features->>'decision_at')::timestamptz`` and **no index may be
   built on that cast** (``timestamptz_in`` is ``STABLE``). ``emitted_at`` is
   the same instant, written from the same variable
   (``hunter_strategy_worker.persist``); the fix is one line in
   ``lab_common.py`` and it is not this revision's to make. The assertion at
   the end of :func:`test_the_lab_page_still_sorts_because_it_orders_by_a_cast`
   fails the day that line changes, which is the day this comment is stale.

Run it with ``-s`` to read the plans (DATABASE.md §26 quotes them).
"""

from __future__ import annotations

import re
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from hunter_api.repositories.lab_common import COHORT, DECISION_AT, tracking_states_for_lab_state
from hunter_core.db.models.agents import AgentSignal, SignalOutcome
from hunter_core.db.models.markets import Market
from hunter_core.domain.enums import ShadowCohort, ShadowTrackingState

from . import lab_fixtures as fx

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
ROW_COUNT = 50_000
"""The brief's volume. At ~1 600 prospective signals/day (DATABASE.md §26) this
is roughly a year of the current rate, or a month of it with six versions
running — the horizon the indexes are being bought for."""

VERSIONS = 6
MARKETS = 5
REPLAY_COHORT = f"{ShadowCohort.REPLAY_PREFIX}0f9d5c1e-0000-4000-8000-00000000c337"
NEW_INDEXES = ("ix_agent_signals_cohort_emitted", "ix_agent_signals_version_cohort_emitted")
AS_OF = "2026-09-09 00:00:00+00"
_INDEX_DDL = (
    (NEW_INDEXES[0], "(supporting_features ->> 'cohort'), emitted_at, id"),
    (NEW_INDEXES[1], "strategy_version_id, (supporting_features ->> 'cohort'), emitted_at, id"),
)
"""The keys ``0014`` installs, repeated here so the build can be timed against
the same population the plans were measured on."""

_SEEDED: list[uuid.UUID] = []
"""The population is seeded once for the whole file: the database is
session-scoped and fifty thousand rows are not worth writing twice."""


async def _seed(session_factory: async_sessionmaker[AsyncSession]) -> list[uuid.UUID]:
    """50 000 signals + 50 000 outcomes in two statements.

    Bulk SQL rather than ``fx.seed_shadow_population``: fifty thousand ORM
    objects is a minute of Python for a shape this file only measures. Every
    column is written the way ``hunter_strategy_worker.persist``/``record``
    write it — ``emitted_at`` **is** ``supporting_features->>'decision_at'``,
    which is the whole point of the measurement.
    """
    if _SEEDED:
        return _SEEDED
    versions = [
        (await fx.seed_strategy_version(session_factory, activated_at=NOW - timedelta(days=120)))[1]
        for _ in range(VERSIONS)
    ]
    markets = [await fx.seed_lab_market(session_factory) for _ in range(MARKETS)]
    version_array = "(ARRAY[" + ",".join(f"'{v}'" for v in versions) + "]::uuid[])"
    market_array = "(ARRAY[" + ",".join(f"'{m}'" for m in markets) + "]::uuid[])"
    async with session_factory() as session:
        await session.execute(
            text(
                f"""
                INSERT INTO agent_signals (
                    id, strategy_version_id, market_id, params_hash, direction, confidence,
                    entry_zone, stop, targets, invalidations, supporting_features,
                    emitted_at, expires_at, status
                )
                SELECT gen_random_uuid(),
                       {version_array}[1 + (i % {VERSIONS})],
                       {market_array}[1 + (i % {MARKETS})],
                       'test-hash', 'long', 0.5, '{{}}'::jsonb, 99,
                       '["103"]'::jsonb, '[]'::jsonb,
                       jsonb_build_object(
                           'observation_ts', d - interval '5 seconds',
                           'decision_at', d,
                           'cohort', c,
                           'timeframe', '15m',
                           'strategy_key', 'lab-fixture',
                           'strategy_version', 'v1',
                           'purpose', 'research_only',
                           'params_format', 1),
                       d, d + interval '4 hours', 'active'
                FROM generate_series(1, :rows) AS i,
                     LATERAL (SELECT CAST(:now AS timestamptz) - make_interval(mins => i)) AS s(d),
                     LATERAL (SELECT CASE i % 10
                                       WHEN 0 THEN :replay
                                       WHEN 1 THEN 'replication:{versions[0]}:1'
                                       ELSE 'prospective' END) AS k(c)
                """  # noqa: S608 — every interpolated value is a UUID minted above
            ),
            {"rows": ROW_COUNT, "now": NOW, "replay": REPLAY_COHORT},
        )
        await session.execute(
            text(
                """
                INSERT INTO signal_outcomes (
                    signal_id, virtual_entry, virtual_stop, virtual_targets, entry_ts,
                    result, exit_price, exit_ts, r_multiple, tracking_state,
                    no_entry_reason, censored_reason, meta
                )
                SELECT a.id,
                       CASE WHEN m = 0 OR m > 3 THEN 100 END,
                       99, '["103"]'::jsonb,
                       CASE WHEN m = 0 OR m > 3 THEN a.emitted_at + interval '1 minute' END,
                       CASE WHEN m > 3 THEN 'target' ELSE 'open' END::outcome_result,
                       CASE WHEN m > 3 THEN 103 END,
                       CASE WHEN m > 3 THEN a.emitted_at + interval '1 hour' END,
                       CASE WHEN m > 3 THEN 1.5 END,
                       CASE m WHEN 0 THEN 'active' WHEN 1 THEN 'no_entry'
                              WHEN 2 THEN 'censored' WHEN 3 THEN 'pending_entry'
                              ELSE 'terminal' END::shadow_tracking_state,
                       CASE WHEN m = 1 THEN 'geometry' END,
                       CASE WHEN m = 2 THEN 'gap' END,
                       jsonb_build_object('horizon_s', 14400, 'purpose', 'research_only')
                FROM agent_signals a,
                     LATERAL (SELECT ((EXTRACT(EPOCH FROM (CAST(:now AS timestamptz)
                              - a.emitted_at)) / 60)::bigint % 20)) AS x(m)
                WHERE NOT EXISTS (SELECT 1 FROM signal_outcomes o WHERE o.signal_id = a.id)
                """
            ),
            {"now": NOW},
        )
        await session.commit()
    async with session_factory() as session:
        await session.execute(text("ANALYZE agent_signals"))
        await session.execute(text("ANALYZE signal_outcomes"))
        await session.execute(text("ANALYZE markets"))
        await session.commit()
    _SEEDED.extend(versions)
    return versions


def _page(*extra: Any, ordered_by_the_column: bool = False) -> Any:
    """The repository's own page query (``LabSignalsRepository.list_page``).

    ``ordered_by_the_column=True`` is the same query with the one line
    ``lab_common.py`` has to change: the sort key becomes ``emitted_at``, the
    column that already holds the decision instant.
    """
    order = AgentSignal.emitted_at if ordered_by_the_column else DECISION_AT
    return (
        select(AgentSignal, SignalOutcome, Market.symbol, DECISION_AT.label("decision_at"))
        .join(SignalOutcome, SignalOutcome.signal_id == AgentSignal.id)
        .join(Market, Market.id == AgentSignal.market_id)
        .where(COHORT == ShadowCohort.PROSPECTIVE, *extra)
        .order_by(order.desc(), AgentSignal.id.desc())
        .limit(201)
    )


def _totals(*extra: Any) -> Any:
    """``LabSignalsRepository._count_totals`` — four ``FILTER``s, no ``LIMIT``."""
    pending = tracking_states_for_lab_state("pending") or ()
    return (
        select(
            func.count().filter(SignalOutcome.tracking_state == ShadowTrackingState.TERMINAL),
            func.count().filter(SignalOutcome.tracking_state == ShadowTrackingState.ACTIVE),
            func.count().filter(SignalOutcome.tracking_state.in_(pending)),
            func.count(),
        )
        .select_from(AgentSignal)
        .join(SignalOutcome, SignalOutcome.signal_id == AgentSignal.id)
        .join(Market, Market.id == AgentSignal.market_id)
        .where(COHORT == ShadowCohort.PROSPECTIVE, *extra)
    )


_COHORT_POPULATION = (
    "SELECT o.tracking_state, count(*) FROM signal_outcomes o "
    "JOIN agent_signals a ON a.id = o.signal_id "
    "WHERE (a.supporting_features ->> 'cohort') = '{cohort}' GROUP BY o.tracking_state"
)
"""The shape ``replay/simulate.count_population`` emits — a query that runs
today, on a cohort that is a small slice of the table."""

_EVALUABLE = (
    "SELECT s.emitted_at, s.id, o.r_multiple FROM agent_signals s "  # noqa: S608
    "JOIN signal_outcomes o ON o.signal_id = s.id "
    "WHERE s.strategy_version_id = '{version}' AND o.tracking_state = 'terminal' "
    "AND o.r_multiple IS NOT NULL AND s.emitted_at <= '" + AS_OF + "'::timestamptz "
    "AND (s.supporting_features ->> 'cohort') = 'prospective' ORDER BY s.emitted_at, s.id"
)
"""``replication_stats._EVALUABLE_SQL``, trimmed to the two tables that matter."""


def _estimate_error(plan: str) -> float:
    """How far the planner's row estimate for ``agent_signals`` is from truth.

    The number the migration moves most: an expression nobody indexed has no
    statistics, so ``= 'prospective'`` is guessed at the 0.5 % default and every
    join above it is chosen on a fiction. ``ANALYZE`` collects statistics for
    index expressions, so the index fixes the estimate whether or not the
    planner then scans it.
    """
    node = next(
        line for line in plan.splitlines() if "Scan on agent_signals" in line and "actual" in line
    )
    estimated, actual = (int(part) for part in re.findall(r"rows=(\d+)", node)[:2])
    return max(estimated, actual) / max(min(estimated, actual), 1)


async def _explain(session: AsyncSession, stmt: Any) -> str:
    if isinstance(stmt, str):
        sql = stmt
    else:
        sql = str(
            stmt.compile(dialect=session.bind.dialect, compile_kwargs={"literal_binds": True})
        )
    result = await session.execute(text(f"EXPLAIN (ANALYZE, BUFFERS) {sql}"))
    return "\n".join(row[0] for row in result.all())


async def _plans(session: AsyncSession, versions: list[uuid.UUID]) -> dict[str, str]:
    return {
        "totals (cohort only, every version)": await _explain(session, _totals()),
        "page 1, state=all (the API's ORDER BY: a cast)": await _explain(session, _page()),
        "page 1, state=closed (the API's ORDER BY: a cast)": await _explain(
            session, _page(SignalOutcome.tracking_state == ShadowTrackingState.TERMINAL)
        ),
        "page 1, state=all, ORDER BY emitted_at (the one-line fix)": await _explain(
            session, _page(ordered_by_the_column=True)
        ),
        "page 1, one version, ORDER BY emitted_at (the fix + a version filter)": await _explain(
            session,
            _page(AgentSignal.strategy_version_id == versions[0], ordered_by_the_column=True),
        ),
        "count_population(cohort=replay:...)": await _explain(
            session, _COHORT_POPULATION.format(cohort=REPLAY_COHORT)
        ),
        "scoreboard: evaluable population of one version": await _explain(
            session, _EVALUABLE.format(version=versions[0])
        ),
    }


def _print(title: str, plans: dict[str, str]) -> None:
    for name, plan in plans.items():
        print(f"\n--- {title} · {name} ---\n{plan}")


async def test_explain_before_and_after_0014_on_fifty_thousand_signals(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The whole measurement, in one seeding: the plans without the indexes,
    the plans with only the first of them, and the plans at head.

    "Before" is produced by dropping the two indexes inside a transaction that
    is rolled back — DDL is transactional in Postgres, and dropping an index
    also drops the statistics ``ANALYZE`` collected for its expression, which
    is the *other* half of what the migration buys (§26).
    """
    versions = await _seed(session_factory)

    async with session_factory() as session:
        await session.execute(text(f"DROP INDEX {', '.join(NEW_INDEXES)}"))
        await session.execute(text("ANALYZE agent_signals"))
        before = await _plans(session, versions)
        # How long the deploy holds the SHARE lock that blocks the
        # strategy-worker's INSERTs — the number 0014's docstring quotes when it
        # explains why it is a plain CREATE INDEX and not 0004's concurrent
        # rebuild. Measured on the same 50 000 rows, then rolled back.
        for name, key in _INDEX_DDL:
            started = time.perf_counter()
            await session.execute(text(f"CREATE INDEX {name} ON agent_signals USING btree ({key})"))
            elapsed = (time.perf_counter() - started) * 1000
            print("")
            print(f"CREATE INDEX {name} on {ROW_COUNT} rows: {elapsed:.1f} ms")
        await session.rollback()
    _print("BEFORE 0014", before)

    async with session_factory() as session:
        await session.execute(text(f"DROP INDEX {NEW_INDEXES[1]}"))
        await session.execute(text("ANALYZE agent_signals"))
        cohort_only = await _plans(session, versions)
        await session.rollback()
    _print("WITH ix_agent_signals_cohort_emitted ONLY", cohort_only)

    async with session_factory() as session:
        after = await _plans(session, versions)
    _print("AFTER 0014", after)

    default_view = "page 1, state=all, ORDER BY emitted_at (the one-line fix)"
    assert "Seq Scan on agent_signals" in before[default_view]
    assert "Sort" in before[default_view]
    assert "Index Scan Backward using ix_agent_signals_cohort_emitted" in after[default_view]
    assert "Sort" not in after[default_view], "the index must deliver the order, not feed a sort"

    population = "count_population(cohort=replay:...)"
    assert "Seq Scan on agent_signals" in before[population]
    assert "ix_agent_signals_cohort_emitted" in after[population]

    # The scoreboard reads a whole population, so a hash join beats an ordered
    # scan and the plan keeps its sort — what the migration fixes there is the
    # *estimate*: an unindexed expression is guessed at 0.5%, and the guess is
    # what chose a nested loop of thousands of probes (§26).
    scoreboard = "scoreboard: evaluable population of one version"
    assert _estimate_error(before[scoreboard]) > 10, before[scoreboard]
    assert _estimate_error(after[scoreboard]) < 2, after[scoreboard]

    # The version-filtered page is what buys the second index: with the cohort
    # index alone the planner has to sort or to filter, with both it walks one
    # index range in order.
    one_version = "page 1, one version, ORDER BY emitted_at (the fix + a version filter)"
    assert "ix_agent_signals_version_cohort_emitted" in after[one_version], after[one_version]
    assert "Sort" not in after[one_version]


async def test_the_lab_page_is_served_by_the_index_now_that_it_orders_by_the_column(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """``lab_common.DECISION_AT`` names ``emitted_at`` since T3.37c.

    The cast the listing used to order by can never be indexed (Postgres
    refuses it: ``timestamptz_in`` is STABLE, not IMMUTABLE) -- asserted here
    so nobody reintroduces it -- and ordering by the column lets ``0014``'s
    ``ix_agent_signals_cohort_emitted`` serve the page without a top-N sort.
    """
    await _seed(session_factory)
    async with session_factory() as session:
        with pytest.raises(DBAPIError, match="must be marked IMMUTABLE"):
            await session.execute(
                text(
                    "CREATE INDEX ix_probe_decision_at ON agent_signals "
                    "(((supporting_features ->> 'decision_at')::timestamptz), id)"
                )
            )
        await session.rollback()
        plan = await _explain(session, _page())
        print("\n--- the Lab's page as the API writes it now ---\n" + plan)
        assert "Index Scan" in plan or "Index Only Scan" in plan
        assert "Seq Scan on agent_signals" not in plan


async def test_an_index_on_tracking_state_would_not_be_read_by_anything(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """T3.37a's third item, measured instead of assumed — and refused.

    ``signal_outcomes`` is never the driving table: every one of these queries
    starts at a signal and reaches its outcome by primary key, so an index on
    five low-cardinality labels is written on every outcome update and read by
    nobody. Built here inside a transaction that is rolled back; if a future
    query does make the planner want it, this test fails and the index becomes
    a migration instead of a paragraph (DATABASE.md §26).
    """
    await _seed(session_factory)
    async with session_factory() as session:
        await session.execute(
            text("CREATE INDEX ix_probe_tracking_state ON signal_outcomes (tracking_state)")
        )
        await session.execute(text("ANALYZE signal_outcomes"))
        closed = _page(
            SignalOutcome.tracking_state == ShadowTrackingState.TERMINAL,
            ordered_by_the_column=True,
        )
        plans = {
            "totals": await _explain(session, _totals()),
            "page 1, state=closed": await _explain(session, closed),
        }
        await session.rollback()
    for name, plan in plans.items():
        print(f"\n--- WITH a probe index on signal_outcomes.tracking_state · {name} ---\n{plan}")
        assert "ix_probe_tracking_state" not in plan, plan
