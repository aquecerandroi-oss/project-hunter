"""The Shadow Lab's durable contracts — migration ``0002_shadow_lab``.

docs/plans/SHADOW-LAB.md "Decisão conjunta" §1, §4 and §6, and the S0 checklist.
Every assertion here is about something the *database* must refuse, because the
Shadow Lab's whole value is that the evidence it collects cannot be quietly
edited afterwards:

- a ``strategy_version`` is frozen by its first activation, in every status;
- ``signal_outcomes.tracking_state`` cannot disagree with ``result``, and a
  ``no_entry``/``censored`` row cannot exist without saying why;
- one tracking per ``(strategy_version_id, market_id, cohort)``, and one episode
  per open outcome;
- ``shadow_outbox`` de-duplicates on ``event_id`` and can find its pending rows
  without a sequential scan.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from hunter_core.domain.enums import ShadowCohort, ShadowTrackingState
from hunter_core.domain.types import uuid7

pytestmark = pytest.mark.integration

_FROZEN = "frozen"
_ACTIVATED_AT = datetime(2026, 9, 5, tzinfo=UTC)
_BAR_CLOSE = datetime(2026, 9, 5, 12, 15, tzinfo=UTC)

_FROZEN_COLUMN_UPDATES: tuple[tuple[str, str], ...] = (
    ("strategy_id", "strategy_id = :other_strategy"),
    ("version", "version = 'v99'"),
    ("code_ref", "code_ref = 'hunter_core.strategies.other'"),
    ("parameters_schema", 'parameters_schema = \'{"type": "object"}\'::jsonb'),
    ("default_parameters", 'default_parameters = \'{"atr_multiple": "2.0"}\'::jsonb'),
    ("params_format", "params_format = 2"),
    ("activated_at", "activated_at = now()"),
    ("activated_at_null", "activated_at = NULL"),
)


@pytest_asyncio.fixture
async def connection(schema_engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """A connection whose work is rolled back — these tests share one database."""
    async with schema_engine.connect() as conn:
        transaction = await conn.begin()
        try:
            yield conn
        finally:
            await transaction.rollback()


async def _strategy(connection: AsyncConnection) -> uuid.UUID:
    strategy_id = uuid7()
    await connection.execute(
        text("INSERT INTO strategies (id, key, name) VALUES (:id, :key, 'Momentum')"),
        {"id": strategy_id, "key": f"momentum-{uuid.uuid4().hex[:8]}"},
    )
    return strategy_id


async def _version(
    connection: AsyncConnection, *, activated: bool, strategy_id: uuid.UUID | None = None
) -> uuid.UUID:
    owner = strategy_id if strategy_id is not None else await _strategy(connection)
    version_id = uuid7()
    await connection.execute(
        text(
            "INSERT INTO strategy_versions "
            "(id, strategy_id, version, status, code_ref, default_parameters, activated_at) "
            "VALUES (:id, :strategy, 'v1', :status, 'hunter_core.strategies.momentum_v1', "
            '\'{"atr_multiple": "1.5"}\'::jsonb, :activated)'
        ),
        {
            "id": version_id,
            "strategy": owner,
            "status": "active" if activated else "draft",
            "activated": _ACTIVATED_AT if activated else None,
        },
    )
    return version_id


async def _market(connection: AsyncConnection) -> uuid.UUID:
    exchange_id, market_id = uuid7(), uuid7()
    await connection.execute(
        text("INSERT INTO exchanges (id, code, name) VALUES (:id, :code, 'Binance')"),
        {"id": exchange_id, "code": f"binance-{uuid.uuid4().hex[:8]}"},
    )
    await connection.execute(
        text(
            "INSERT INTO markets (id, exchange_id, symbol, market_type) "
            "VALUES (:id, :ex, 'BTCUSDT', 'perpetual')"
        ),
        {"id": market_id, "ex": exchange_id},
    )
    return market_id


async def _signal(
    connection: AsyncConnection, version_id: uuid.UUID, market_id: uuid.UUID | None = None
) -> uuid.UUID:
    signal_id = uuid7()
    await connection.execute(
        text(
            "INSERT INTO agent_signals "
            "(id, strategy_version_id, market_id, params_hash, direction, confidence) "
            "VALUES (:id, :version, :market, 'deadbeef', 'long', 0.5)"
        ),
        {
            "id": signal_id,
            "version": version_id,
            "market": market_id if market_id is not None else await _market(connection),
        },
    )
    return signal_id


async def _outcome_row(connection: AsyncConnection, signal_id: uuid.UUID) -> None:
    """The default outcome of an existing signal: ``pending_entry``, no result."""
    await connection.execute(
        text("INSERT INTO signal_outcomes (signal_id) VALUES (:signal_id)"),
        {"signal_id": signal_id},
    )


async def _outcome(connection: AsyncConnection, **columns: Any) -> uuid.UUID:
    """One ``signal_outcomes`` row for a fresh signal, with ``columns`` set."""
    signal_id = await _signal(connection, await _version(connection, activated=True))
    names = "".join(f", {name}" for name in columns)
    placeholders = "".join(f", :{name}" for name in columns)
    await connection.execute(
        text(
            f"INSERT INTO signal_outcomes (signal_id{names}) "  # noqa: S608
            f"VALUES (:signal_id{placeholders})"
        ),
        {"signal_id": signal_id, **columns},
    )
    return signal_id


# --------------------------------------------------------------------------
# strategy_versions: frozen by the first activation
# --------------------------------------------------------------------------


async def test_a_draft_version_is_still_editable(connection: AsyncConnection) -> None:
    """Freezing starts at activation; a draft is where the design is still moving."""
    version_id = await _version(connection, activated=False)
    await connection.execute(
        text(
            'UPDATE strategy_versions SET default_parameters = \'{"atr_multiple": "2"}\'::jsonb, '
            "code_ref = 'other', params_format = 1 WHERE id = :id"
        ),
        {"id": version_id},
    )


async def test_the_first_activation_is_allowed(connection: AsyncConnection) -> None:
    version_id = await _version(connection, activated=False)
    await connection.execute(
        text("UPDATE strategy_versions SET status = 'active', activated_at = now() WHERE id = :id"),
        {"id": version_id},
    )


@pytest.mark.parametrize(("label", "assignment"), _FROZEN_COLUMN_UPDATES)
async def test_every_experiment_defining_column_is_frozen_after_activation(
    connection: AsyncConnection, label: str, assignment: str
) -> None:
    """Content that identifies or determines the experiment cannot change — and
    that includes un-activating the version, which would otherwise thaw it."""
    assert label
    version_id = await _version(connection, activated=True)
    other_strategy = await _strategy(connection)
    with pytest.raises(DBAPIError, match=_FROZEN):
        await connection.execute(
            text(f"UPDATE strategy_versions SET {assignment} WHERE id = :id"),  # noqa: S608
            {"id": version_id, "other_strategy": other_strategy},
        )


async def test_status_and_changelog_stay_mutable(connection: AsyncConnection) -> None:
    version_id = await _version(connection, activated=True)
    await connection.execute(
        text(
            "UPDATE strategy_versions SET status = 'deprecated', changelog = 'superseded by v2', "
            "deprecated_at = now() WHERE id = :id"
        ),
        {"id": version_id},
    )


async def test_a_deprecated_version_is_still_frozen(connection: AsyncConnection) -> None:
    version_id = await _version(connection, activated=True)
    await connection.execute(
        text("UPDATE strategy_versions SET status = 'deprecated' WHERE id = :id"),
        {"id": version_id},
    )
    with pytest.raises(DBAPIError, match=_FROZEN):
        await connection.execute(
            text("UPDATE strategy_versions SET code_ref = 'rewritten' WHERE id = :id"),
            {"id": version_id},
        )


async def test_a_reactivated_version_is_still_frozen(connection: AsyncConnection) -> None:
    version_id = await _version(connection, activated=True)
    await connection.execute(
        text("UPDATE strategy_versions SET status = 'deprecated' WHERE id = :id"),
        {"id": version_id},
    )
    await connection.execute(
        text("UPDATE strategy_versions SET status = 'active' WHERE id = :id"), {"id": version_id}
    )
    with pytest.raises(DBAPIError, match=_FROZEN):
        await connection.execute(
            text(
                "UPDATE strategy_versions "
                'SET default_parameters = \'{"atr_multiple": "9"}\'::jsonb WHERE id = :id'
            ),
            {"id": version_id},
        )


async def test_rewriting_a_frozen_json_with_the_same_value_is_not_a_change(
    connection: AsyncConnection,
) -> None:
    """The guard compares values, not spellings: reordering the keys of an
    identical ``default_parameters`` is a no-op, not an attempt to rewrite it."""
    version_id = await _version(connection, activated=True)
    await connection.execute(
        text(
            "UPDATE strategy_versions "
            'SET default_parameters = \'{"atr_multiple":"1.5"}\'::jsonb WHERE id = :id'
        ),
        {"id": version_id},
    )


async def test_an_activated_version_cannot_be_deleted(connection: AsyncConnection) -> None:
    """``UPDATE`` is not the only way to rewrite history: DELETE + INSERT of the
    same id would replace an activated version, and ``hunter_worker`` holds
    ``DELETE`` on this table."""
    version_id = await _version(connection, activated=True)
    with pytest.raises(DBAPIError, match=_FROZEN):
        await connection.execute(
            text("DELETE FROM strategy_versions WHERE id = :id"), {"id": version_id}
        )


async def test_deleting_the_parent_strategy_cannot_erase_an_activated_version(
    connection: AsyncConnection,
) -> None:
    """``strategies`` cascades into ``strategy_versions``; the cascade hits the
    same guard, so the whole ``DELETE`` fails. Removing the catalogue entry is
    not a back door around the freeze (Astra's review, round 2)."""
    strategy_id = await _strategy(connection)
    await _version(connection, activated=True, strategy_id=strategy_id)
    with pytest.raises(DBAPIError, match=_FROZEN):
        await connection.execute(text("DELETE FROM strategies WHERE id = :id"), {"id": strategy_id})


async def test_a_draft_version_can_still_be_deleted(connection: AsyncConnection) -> None:
    version_id = await _version(connection, activated=False)
    await connection.execute(
        text("DELETE FROM strategy_versions WHERE id = :id"), {"id": version_id}
    )


# --------------------------------------------------------------------------
# signal_outcomes: tracking_state, reasons and their coherence with result
# --------------------------------------------------------------------------


async def test_a_new_outcome_starts_pending_entry_with_an_empty_meta(
    connection: AsyncConnection,
) -> None:
    signal_id = await _outcome(connection)
    row = (
        await connection.execute(
            text("SELECT tracking_state, result, meta FROM signal_outcomes WHERE signal_id = :id"),
            {"id": signal_id},
        )
    ).one()
    assert row.tracking_state == ShadowTrackingState.PENDING_ENTRY
    assert row.result == "open"
    assert row.meta == {}


@pytest.mark.parametrize(
    "state", [ShadowTrackingState.NO_ENTRY.value, ShadowTrackingState.CENSORED.value]
)
async def test_no_entry_and_censored_require_their_reason(
    connection: AsyncConnection, state: str
) -> None:
    with pytest.raises(IntegrityError, match="reason"):
        await _outcome(connection, tracking_state=state)


async def test_a_reason_cannot_be_empty(connection: AsyncConnection) -> None:
    """``NOT NULL`` alone would accept ``''``, which records nothing."""
    with pytest.raises(IntegrityError, match="reason"):
        await _outcome(connection, tracking_state="no_entry", no_entry_reason="")


async def test_a_reason_cannot_be_attached_to_an_unrelated_state(
    connection: AsyncConnection,
) -> None:
    with pytest.raises(IntegrityError, match="reason"):
        await _outcome(connection, tracking_state="active", no_entry_reason="late")


async def test_two_reasons_at_once_are_refused(connection: AsyncConnection) -> None:
    with pytest.raises(IntegrityError, match="reason"):
        await _outcome(
            connection,
            tracking_state="no_entry",
            no_entry_reason="late",
            censored_reason="gap",
        )


async def test_no_entry_and_censored_keep_result_open(connection: AsyncConnection) -> None:
    """``no_entry`` never counts as open and censorship never becomes ``expired``:
    both are states of the *tracking*, and the financial ``result`` of either is
    simply not known (SHADOW-LAB.md §4)."""
    await _outcome(connection, tracking_state="no_entry", no_entry_reason="late")
    await _outcome(connection, tracking_state="censored", censored_reason="gap_irrecoverable")


@pytest.mark.parametrize("state", ["pending_entry", "active", "no_entry", "censored"])
async def test_a_resolved_result_requires_a_terminal_tracking(
    connection: AsyncConnection, state: str
) -> None:
    reasons = {"no_entry": "no_entry_reason", "censored": "censored_reason"}
    extra = {reasons[state]: "late"} if state in reasons else {}
    with pytest.raises(IntegrityError, match="tracking_state"):
        await _outcome(connection, tracking_state=state, result="target", **extra)


async def test_a_terminal_tracking_requires_a_resolved_result(
    connection: AsyncConnection,
) -> None:
    with pytest.raises(IntegrityError, match="tracking_state"):
        await _outcome(connection, tracking_state="terminal", result="open")


async def test_a_terminal_tracking_with_a_resolved_result_is_accepted(
    connection: AsyncConnection,
) -> None:
    for result in ("target", "stop", "expired", "invalidated"):
        await _outcome(connection, tracking_state="terminal", result=result)


# --------------------------------------------------------------------------
# shadow_episodes
# --------------------------------------------------------------------------


async def _episode(connection: AsyncConnection, **columns: Any) -> None:
    payload: dict[str, Any] = {
        "id": uuid7(),
        "episode_id": uuid7(),
        "last_bar_close": _BAR_CLOSE,
        **columns,
    }
    names = ", ".join(payload)
    placeholders = ", ".join(f":{name}" for name in payload)
    await connection.execute(
        text(f"INSERT INTO shadow_episodes ({names}) VALUES ({placeholders})"),  # noqa: S608
        payload,
    )


async def test_one_tracking_slot_per_version_market_and_cohort(
    connection: AsyncConnection,
) -> None:
    version_id = await _version(connection, activated=True)
    market_id = await _market(connection)
    await _episode(
        connection, strategy_version_id=version_id, market_id=market_id, cohort="prospective"
    )
    with pytest.raises(IntegrityError, match="uq_shadow_episodes"):
        await _episode(
            connection, strategy_version_id=version_id, market_id=market_id, cohort="prospective"
        )


async def test_a_replay_cohort_never_occupies_the_prospective_slot(
    connection: AsyncConnection,
) -> None:
    version_id = await _version(connection, activated=True)
    market_id = await _market(connection)
    run = ShadowCohort.replay(uuid7())
    for cohort in ("prospective", run):
        await _episode(
            connection, strategy_version_id=version_id, market_id=market_id, cohort=cohort
        )


@pytest.mark.parametrize(
    "cohort",
    [
        "",
        "replay",
        "replay:",
        "replay:not-a-uuid",
        "backfill",
        # a trailing newline: Python's ``$`` used to accept these, Postgres never
        # did, and the disagreement is what Astra's review caught
        "prospective\n",
        f"replay:{uuid7()}\n",
    ],
)
async def test_an_unparseable_cohort_is_refused(connection: AsyncConnection, cohort: str) -> None:
    """``prospective`` or ``replay:<run_id>`` — nothing else, so a typo cannot
    silently create a third population nobody reports on."""
    version_id = await _version(connection, activated=True)
    with pytest.raises(IntegrityError, match="cohort"):
        await _episode(
            connection,
            strategy_version_id=version_id,
            market_id=await _market(connection),
            cohort=cohort,
        )


async def test_an_episode_can_only_hold_a_real_signal(connection: AsyncConnection) -> None:
    version_id = await _version(connection, activated=True)
    with pytest.raises(IntegrityError, match="fk_shadow_episodes_open_outcome_signal_id"):
        await _episode(
            connection,
            strategy_version_id=version_id,
            market_id=await _market(connection),
            cohort="prospective",
            open_outcome_signal_id=uuid7(),
        )


async def test_an_episode_cannot_hold_a_signal_of_another_market(
    connection: AsyncConnection,
) -> None:
    """Raised by Astra's review: with a single-column FK this was accepted.

    A BTC signal sitting in the ETH slot satisfies "the signal exists" and
    nothing else: ``tracking_hold`` would then keep ETH's candles while BTC —
    the market the outcome actually needs to be resolved — was free to leave the
    monitored universe and lose its history.
    """
    version_id = await _version(connection, activated=True)
    signal_market = await _market(connection)
    signal_id = await _signal(connection, version_id, signal_market)
    await _outcome_row(connection, signal_id)

    with pytest.raises(IntegrityError, match="fk_shadow_episodes_open_outcome_signal_id"):
        await _episode(
            connection,
            strategy_version_id=version_id,
            market_id=await _market(connection),  # a different market
            cohort="prospective",
            open_outcome_signal_id=signal_id,
        )


async def test_an_episode_cannot_hold_a_signal_nobody_is_tracking(
    connection: AsyncConnection,
) -> None:
    """The slot holds an *outcome*; a signal with no ``signal_outcomes`` row is a
    decision nobody is following, and a hold on its market would never end."""
    version_id = await _version(connection, activated=True)
    market_id = await _market(connection)
    signal_id = await _signal(connection, version_id, market_id)

    # a savepoint: the refusal below poisons the transaction, and the point of
    # this test is what happens *after* the outcome row finally exists
    savepoint = await connection.begin_nested()
    with pytest.raises(IntegrityError, match="fk_shadow_episodes_open_outcome_signal_id"):
        await _episode(
            connection,
            strategy_version_id=version_id,
            market_id=market_id,
            cohort="prospective",
            open_outcome_signal_id=signal_id,
        )
    await savepoint.rollback()

    await _outcome_row(connection, signal_id)
    await _episode(
        connection,
        strategy_version_id=version_id,
        market_id=market_id,
        cohort="prospective",
        open_outcome_signal_id=signal_id,
    )


async def test_two_episodes_cannot_hold_the_same_open_outcome(
    connection: AsyncConnection,
) -> None:
    version_id = await _version(connection, activated=True)
    market_id = await _market(connection)
    signal_id = await _signal(connection, version_id, market_id)
    await _outcome_row(connection, signal_id)
    await _episode(
        connection,
        strategy_version_id=version_id,
        market_id=market_id,
        cohort="prospective",
        open_outcome_signal_id=signal_id,
    )
    with pytest.raises(IntegrityError, match="uq_shadow_episodes_open_outcome"):
        await _episode(
            connection,
            strategy_version_id=version_id,
            market_id=market_id,
            cohort=ShadowCohort.replay(uuid7()),
            open_outcome_signal_id=signal_id,
        )


async def test_an_episode_cannot_hold_a_signal_of_another_strategy_version(
    connection: AsyncConnection,
) -> None:
    """The other half of the composite FK: right market, wrong version.

    v1 and v2 run in parallel on the same market (SHADOW-LAB.md §1); a slot that
    could hold the other version's outcome would report one version's evidence
    under the other's name.
    """
    market_id = await _market(connection)
    other_version = await _version(connection, activated=True)
    signal_id = await _signal(connection, other_version, market_id)
    await _outcome_row(connection, signal_id)

    with pytest.raises(IntegrityError, match="fk_shadow_episodes_open_outcome_signal_id"):
        await _episode(
            connection,
            strategy_version_id=await _version(connection, activated=True),
            market_id=market_id,
            cohort="prospective",
            open_outcome_signal_id=signal_id,
        )


async def test_removing_the_outcome_only_releases_the_slot(
    connection: AsyncConnection,
) -> None:
    """``ON DELETE SET NULL`` on the link, never on the checkpoint.

    Both foreign keys name the link column, so a deleted signal (which cascades
    to its outcome) leaves the episode's version, market, cohort and
    ``last_bar_close`` intact — the slot goes idle, it does not lose its place.
    """
    version_id = await _version(connection, activated=True)
    market_id = await _market(connection)
    signal_id = await _signal(connection, version_id, market_id)
    await _outcome_row(connection, signal_id)
    await _episode(
        connection,
        strategy_version_id=version_id,
        market_id=market_id,
        cohort="prospective",
        open_outcome_signal_id=signal_id,
    )

    await connection.execute(text("DELETE FROM agent_signals WHERE id = :id"), {"id": signal_id})

    row = (
        await connection.execute(
            text(
                "SELECT open_outcome_signal_id, strategy_version_id, market_id, cohort, "
                "last_bar_close FROM shadow_episodes WHERE strategy_version_id = :version"
            ),
            {"version": version_id},
        )
    ).one()
    assert row.open_outcome_signal_id is None
    assert row.strategy_version_id == version_id
    assert row.market_id == market_id
    assert row.cohort == "prospective"
    assert row.last_bar_close == _BAR_CLOSE


async def test_idle_episodes_do_not_compete_for_the_partial_unique_index(
    connection: AsyncConnection,
) -> None:
    version_id = await _version(connection, activated=True)
    for _ in range(2):
        await _episode(
            connection,
            strategy_version_id=version_id,
            market_id=await _market(connection),
            cohort="prospective",
        )


async def test_the_tracking_hold_query_has_an_index(connection: AsyncConnection) -> None:
    """``tracking_hold`` (SHADOW-LAB.md §8) is a lookup by market over open
    trackings; the market-worker runs it on every universe refresh."""
    definitions = (
        (
            await connection.execute(
                text("SELECT indexdef FROM pg_indexes WHERE tablename = 'shadow_episodes'")
            )
        )
        .scalars()
        .all()
    )
    partial = [d for d in definitions if "open_outcome_signal_id IS NOT NULL" in d]
    assert any("market_id" in definition for definition in partial), definitions


# --------------------------------------------------------------------------
# shadow_outbox
# --------------------------------------------------------------------------

_QUEUE_ONE = text(
    "INSERT INTO shadow_outbox (event_id, stream, payload) "
    "VALUES (:event_id, 'shadow.signals.emitted', '{}'::jsonb)"
)


async def test_an_event_is_only_queued_once(connection: AsyncConnection) -> None:
    """Redelivery of the same shadow decision must not publish twice."""
    event_id = uuid7()
    await connection.execute(_QUEUE_ONE, {"event_id": event_id})
    with pytest.raises(IntegrityError, match="uq_shadow_outbox_event_id"):
        await connection.execute(_QUEUE_ONE, {"event_id": event_id})


async def test_the_dispatcher_finds_pending_rows_through_a_partial_index(
    connection: AsyncConnection,
) -> None:
    definitions = (
        (
            await connection.execute(
                text("SELECT indexdef FROM pg_indexes WHERE tablename = 'shadow_outbox'")
            )
        )
        .scalars()
        .all()
    )
    assert any("dispatched_at IS NULL" in definition for definition in definitions), definitions
    # ``0004``: the same widening ``outbox_events`` got. The two queues are
    # shape-identical on purpose (16.4/17.5) and are drained in the same
    # ``(created_at, id)`` order, so their pending index must not diverge.
    assert any(
        "(dispatched_at IS NULL)" in definition and "(created_at, id)" in definition
        for definition in definitions
    ), definitions


async def test_an_outbox_row_starts_pending_with_no_attempts(
    connection: AsyncConnection,
) -> None:
    event_id = uuid7()
    await connection.execute(_QUEUE_ONE, {"event_id": event_id})
    row = (
        await connection.execute(
            text(
                "SELECT dispatched_at, attempts, last_error FROM shadow_outbox "
                "WHERE event_id = :event_id"
            ),
            {"event_id": event_id},
        )
    ).one()
    assert row.dispatched_at is None
    assert row.attempts == 0
    assert row.last_error is None


async def test_attempts_can_never_go_negative(connection: AsyncConnection) -> None:
    with pytest.raises(IntegrityError, match="attempts"):
        await connection.execute(
            text(
                "INSERT INTO shadow_outbox (event_id, stream, payload, attempts) "
                "VALUES (:event_id, 'shadow.signals.emitted', '{}'::jsonb, -1)"
            ),
            {"event_id": uuid7()},
        )


# --------------------------------------------------------------------------
# roles
# --------------------------------------------------------------------------


async def test_the_worker_can_actually_queue_an_event(schema_engine: AsyncEngine) -> None:
    """A table grant is not enough here.

    ``shadow_outbox.id`` is ``BIGSERIAL`` — the first sequence in this schema —
    so the writing role also needs ``USAGE`` on ``shadow_outbox_id_seq``.
    ``has_table_privilege`` would happily report ``INSERT`` while every insert
    failed with "permission denied for sequence", so this test writes a row as
    the role instead of asking about it.
    """
    async with schema_engine.begin() as connection:
        await connection.execute(text("GRANT hunter_worker TO CURRENT_USER"))
    async with schema_engine.connect() as connection:
        await connection.begin()
        await connection.execute(text("SET LOCAL ROLE hunter_worker"))
        await connection.execute(_QUEUE_ONE, {"event_id": uuid7()})
        await connection.rollback()


async def test_the_shadow_tables_are_system_tables_the_api_can_only_read(
    schema_engine: AsyncEngine,
) -> None:
    """No ``organization_id``, like ``agent_signals``/``signal_outcomes``: shadow
    research is global. The API reads it; only ``hunter_worker`` writes it."""
    async with schema_engine.connect() as conn:
        for table in ("shadow_episodes", "shadow_outbox"):
            tenant_column = await conn.scalar(
                text(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name = 'organization_id'"
                ),
                {"t": table},
            )
            assert tenant_column == 0
            assert await conn.scalar(
                text("SELECT has_table_privilege('hunter_app', :t, 'SELECT')"), {"t": table}
            )
            for privilege in ("INSERT", "UPDATE", "DELETE"):
                assert not await conn.scalar(
                    text("SELECT has_table_privilege('hunter_app', :t, :p)"),
                    {"t": table, "p": privilege},
                ), f"hunter_app can {privilege} {table}"
                assert await conn.scalar(
                    text("SELECT has_table_privilege('hunter_worker', :t, :p)"),
                    {"t": table, "p": privilege},
                ), f"hunter_worker cannot {privilege} {table}"
