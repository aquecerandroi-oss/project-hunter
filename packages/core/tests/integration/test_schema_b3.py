"""``0071_b3_robot`` (R3 of ``docs/design/robo-b3-mt5.md``) — its own database.

What is proved, against the frozen contract ``docs/RISK_ENGINE_B3.md``:
the catalogue (24 tenant tables, RLS forced, ``tenant_isolation``, indexes led by
``organization_id``, money ``NUMERIC(28,10)``, time ``timestamptz``); the enum
labels verbatim (§1.2); grants (no ``DELETE``, append-only and retire-only);
**tenant isolation** (org B reads none of org A's rows in any table, cannot write
under A's id, and sees nothing without ``app.current_org``); every mutation
needs an ``audit_logs`` row of the same transaction; ``client_order_id`` is the
§1.1 formula computed by the database; machine A (one grant per account, token +
1, no renewal, DB clock), machine B (transitions, terminals, write-once decision
and claim, the 30 s approval), the claim (identity half, and two executors —
one wins, F32), the robot kill switch (transition required; who releases what),
machine C and the SLTP slot (I-X-3, I-SL-1, I-SL-3, one request in flight); the
downgrade refuses with rows and round-trips clean; ``alembic check``.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pytest
import pytest_asyncio
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from hunter_core.db.models import tenant_tables
from hunter_core.domain.b3_enums import B3_ENUMS

from .conftest import alembic_config, async_engine, create_database, migration_ddl

pytestmark = pytest.mark.integration

REVISION = "0071_b3_robot"
PREVIOUS = "0069_meme_absorb_semdump_arm"
DDL = migration_ddl("b3_robot")
TABLES: tuple[str, ...] = DDL.B3_TENANT_TABLES


@pytest.fixture(scope="module")
def upgraded(container_url: str) -> Iterator[str]:
    """This revision by name, not ``head``: the held ``0070`` may share ``0069``."""
    url = asyncio.run(create_database(container_url, "hunter_schema_b3"))
    command.upgrade(alembic_config(url), REVISION)
    yield url


@pytest_asyncio.fixture
async def engine(upgraded: str) -> AsyncIterator[AsyncEngine]:
    created = async_engine(upgraded)
    try:
        yield created
    finally:
        await created.dispose()


def _hex(seed: uuid.UUID, salt: str) -> str:
    return hashlib.sha256(seed.bytes + salt.encode()).hexdigest()


def client_order_id(proposal_id: uuid.UUID) -> str:
    """The robot's side of §1.1, byte for byte."""
    digest = hashlib.sha256(proposal_id.bytes).digest()
    return "HB" + base64.b32encode(digest).decode().rstrip("=").upper()[:16]


async def audit(conn: AsyncConnection, org: uuid.UUID, *entities: tuple[str, Any]) -> None:
    for table, entity in entities:
        await conn.execute(
            text(
                "INSERT INTO audit_logs (id, organization_id, actor_type, action, entity_type, "
                "entity_id) VALUES (:id, :org, 'system', 'b3.test', :t, :e)"
            ),
            {"id": uuid.uuid4(), "org": org, "t": table, "e": entity},
        )


@asynccontextmanager
async def as_app(engine: AsyncEngine, org: uuid.UUID | None) -> AsyncGenerator[AsyncConnection]:
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL ROLE hunter_app"))
        if org is not None:
            await conn.execute(
                text("SELECT set_config('app.current_org', :o, true)"), {"o": str(org)}
            )
        yield conn


@dataclass
class World:
    """One organization with a registered account, an instance, limits v1, a spec
    pin and a management grant — written as the owner, audited."""

    org: uuid.UUID = field(default_factory=uuid.uuid4)
    account_id: uuid.UUID = field(default_factory=uuid.uuid4)
    instance: uuid.UUID = field(default_factory=uuid.uuid4)
    profile: uuid.UUID = field(default_factory=uuid.uuid4)
    pin: uuid.UUID = field(default_factory=uuid.uuid4)
    authority_row: uuid.UUID = field(default_factory=uuid.uuid4)
    authority_id: uuid.UUID = field(default_factory=uuid.uuid4)

    @property
    def account(self) -> str:
        return _hex(self.org, "account")

    @property
    def host(self) -> str:
        return _hex(self.org, "host")

    def params(self, **extra: Any) -> dict[str, Any]:
        return {
            "org": self.org, "acc": self.account, "host": self.host, "inst": self.instance,
            "pin": self.pin, "auth_row": self.authority_row, "auth": self.authority_id, **extra,
        }  # fmt: skip


async def make_world(engine: AsyncEngine) -> World:
    w = World()
    p = w.params(acc_id=w.account_id, prof=w.profile, slug=f"b3-{w.org.hex[:10]}")
    async with engine.begin() as c:
        await c.execute(
            text("INSERT INTO organizations (id, slug, name) VALUES (:org, :slug, :slug)"), p
        )
        await c.execute(
            text(
                "INSERT INTO b3_robot_accounts (id, organization_id, registered_account_hash, "
                "authorized_host_hash) VALUES (:acc_id, :org, :acc, :host)"
            ),
            p,
        )
        await c.execute(
            text(
                "INSERT INTO b3_robot_instances (instance_id, organization_id, host_hash, "
                "account_hash_seen, started_at) VALUES (:inst, :org, :host, :acc, now())"
            ),
            p,
        )
        await c.execute(
            text(
                "INSERT INTO b3_risk_profiles (id, organization_id, limits_version, limits) "
                """VALUES (:prof, :org, 1, '{"daily_loss_limit_brl": "9000"}')"""
            ),
            p,
        )
        await c.execute(
            text(
                "INSERT INTO b3_spec_pins (id, organization_id, account_hash, symbol, "
                "trade_tick_size, trade_tick_value, point, digits, volume_min, volume_step, "
                "volume_max, trade_mode, filling_mode, expiration_mode, account_margin_mode, "
                "terminal_version, package_version, order_lifecycle_proven, comment_preserved, "
                "stale_ticket_rejection_proven, evidence) VALUES (:pin, :org, :acc, 'WINZ26', 5, "
                "0.2, 1, 0, 1, 1, 10, 'FULL', 'RETURN', 'DAY', 'NETTING', '5.0.4', '5.0.5', true, "
                "true, false, '{}')"
            ),
            p,
        )
        await c.execute(
            text(
                "INSERT INTO b3_robot_authority (id, organization_id, account_hash, authority_id, "
                "host_hash, instance_id, session_date, fencing_token, granted_at, "
                "authority_expires_at) VALUES (:auth_row, :org, :acc, :auth, :host, :inst, "
                "current_date, 1, '2000-01-01', now() + interval '1 hour')"
            ),
            p,
        )
        await audit(
            c, w.org, ("b3_robot_accounts", w.account_id), ("b3_robot_instances", w.instance),
            ("b3_risk_profiles", w.profile), ("b3_spec_pins", w.pin),
            ("b3_robot_authority", w.authority_row),
        )  # fmt: skip
    return w


async def arm(engine: AsyncEngine, w: World, limits_version: int = 1) -> None:
    async with as_app(engine, w.org) as c:
        await c.execute(
            text(
                "UPDATE b3_robot_authority SET phase = 'entries', armed_at = now(), "
                "armed_strategy_key = 'h038', armed_strategy_version = 1, armed_params_hash = 'p', "
                "limits_version = :lv, spec_pin_id = :pin WHERE id = :auth_row"
            ),
            w.params(lv=limits_version),
        )
        await audit(c, w.org, ("b3_robot_authority", w.authority_row))


async def propose(
    engine: AsyncEngine, w: World, *, approve: bool = True, age_s: int = 0
) -> uuid.UUID:
    proposal = uuid.uuid4()
    p = w.params(prop=proposal, win=proposal.hex, age=age_s, dec=decision_json(proposal, w))
    async with as_app(engine, w.org) as c:
        await c.execute(
            text(
                "INSERT INTO b3_entry_proposals (proposal_id, organization_id, account_hash, "
                "instance_id, strategy_key, strategy_version, params_hash, session_date, window_id, "
                "symbol, side, requested_contracts, ref_price, stop_price, signal_published_at, "
                "signal_deadline_utc, entry_window_start_utc, entry_window_end_utc) VALUES (:prop, "
                ":org, :acc, :inst, 'h038', 1, 'p', current_date, :win, 'WINZ26', 'buy', 1, "
                "130000, 129350, now(), now(), now(), now() + interval '5 minutes')"
            ),
            p,
        )
        await c.execute(
            text(
                "INSERT INTO b3_entry_intents (proposal_id, organization_id, account_hash, "
                "instance_id) VALUES (:prop, :org, :acc, :inst)"
            ),
            p,
        )
        await audit(c, w.org, ("b3_entry_proposals", proposal), ("b3_entry_intents", proposal))
    if approve:
        async with as_app(engine, w.org) as c:
            await c.execute(
                text(
                    "UPDATE b3_entry_intents SET status = 'approved', decision = CAST(:dec AS jsonb) "
                    "|| jsonb_build_object('as_of', now() - make_interval(secs => :age), "
                    "'approved_at', now() - make_interval(secs => :age), 'expires_at', "
                    "now() - make_interval(secs => :age) + interval '30 seconds'), "
                    "decided_at = now(), approved_at = now() - make_interval(secs => :age), "
                    "expires_at = now() - make_interval(secs => :age) + interval '30 seconds', "
                    "limits_version = 1, grid_version = 1, spec_pin_id = :pin, n_final = 1, "
                    "limit_price = 130005 WHERE proposal_id = :prop"
                ),
                p,
            )
            await audit(c, w.org, ("b3_entry_intents", proposal))
    return proposal


def decision_json(proposal: uuid.UUID, w: World, *, approved: bool = True) -> str:
    """A ``RiskDecision`` as R1 serializes it (``hunter_risk_b3.decision``, §8.4)."""
    checks = [{"id": i, "name": f"c{i}", "state": "passed"} for i in range(1, 26)]
    return json.dumps({
        "kind": "entry", "proposal_id": str(proposal), "approved": approved,
        "reasons": [], "checks": checks, "kill_switch_effective": "ACTIVE", "triggers": [],
        "sizing": {"n_final": 1, "limit_price": "130005"}, "limits_version": "1",
        "grid_version": "1", "spec_pin_id": str(w.pin), "as_of": "2026-11-03T13:00:00Z",
        "approved_at": "2026-11-03T13:00:00Z", "expires_at": "2026-11-03T13:00:30Z",
    })  # fmt: skip


_APPROVE_WITH = (
    "UPDATE b3_entry_intents SET status = 'approved', decision = {decision}, decided_at = now(), "
    "approved_at = now(), expires_at = now() + interval '30 seconds', limits_version = 1, "
    "grid_version = 1, spec_pin_id = :pin, n_final = 1, limit_price = CAST(:lp AS numeric) "
    "WHERE proposal_id = :prop"
)
"""An approval whose decision SQL is substituted by the test (fixed fragments only)."""

_CLAIM = text(
    "UPDATE b3_entry_intents SET status = 'submitting', claimed_at = now(), "
    "claim_instance_id = :inst, claim_fencing_token = :tok, "
    "send_deadline_utc = LEAST(clock_timestamp() + interval '3 seconds', expires_at) "
    "WHERE proposal_id = :prop AND status = 'approved'"
)


async def claim(engine: AsyncEngine, w: World, proposal: uuid.UUID, token: int = 1) -> int:
    async with as_app(engine, w.org) as c:
        result = await c.execute(_CLAIM, w.params(prop=proposal, tok=token))
        await audit(c, w.org, ("b3_entry_intents", proposal))
        return result.rowcount


async def scalar(engine: AsyncEngine, sql: str, params: dict[str, Any] | None = None) -> Any:
    async with engine.connect() as c:
        return await c.scalar(text(sql), params or {})


_POPULATE = (
    ("b3_holidays", "INSERT INTO b3_holidays (id, organization_id, holiday_date, source_note) "
     "VALUES (:id, :org, '2026-11-20', 'B3 calendar 2026')"),
    ("b3_session_grids", "INSERT INTO b3_session_grids (id, organization_id, symbol_root, "
     "grid_version, valid_from, open_local, close_local, session_end_local, source_note) VALUES "
     "(:id, :org, 'WIN', 1, '2026-11-03', '09:00', '18:25', '18:30', 'OC 050/2026-VNC')"),
    ("b3_contracts", "INSERT INTO b3_contracts (id, organization_id, symbol, root, expiry_date, "
     "valid_from, valid_until, source_note) VALUES (:id, :org, 'WINZ26', 'WIN', '2026-12-16', "
     "'2026-10-15', '2026-12-10', 'B3 calendar')"),
    ("b3_fee_schedules", "INSERT INTO b3_fee_schedules (id, organization_id, symbol_root, "
     "per_leg_brl, valid_from, source, source_date) VALUES (:id, :org, 'WIN', 0.256, "
     "'2026-10-01', 'B3 tarifas', '2026-10-01')"),
    ("b3_strategy_magics", "INSERT INTO b3_strategy_magics (id, organization_id, strategy_key, "
     "strategy_version, magic) VALUES (:id, :org, 'h038', 1, 38001)"),
    ("b3_management_epochs", "INSERT INTO b3_management_epochs (epoch_id, organization_id, "
     "account_hash, instance_id, authority_id, host_hash) VALUES (:id, :org, :acc, :inst, :auth, :host)"),
    ("b3_robot_heartbeats", "INSERT INTO b3_robot_heartbeats (instance_id, organization_id, "
     "account_hash, as_of, payload) VALUES (:inst, :org, :acc, now(), '{\"v\": 1}')"),
    ("b3_robot_events", "INSERT INTO b3_robot_events (id, organization_id, event_id, account_hash, "
     "instance_id, kind, payload_sha256) VALUES (:id, :org, :id, :acc, :inst, 'heartbeat', :acc)"),
    ("b3_deals", "INSERT INTO b3_deals (id, organization_id, account_hash, deal_ticket, position_id, "
     "symbol, side, entry, reason, volume, price, commission, fee, swap, profit, magic, time_msc, "
     "deal_time) VALUES (:id, :org, :acc, 9001, 88, 'WINZ26', 'buy', 'DEAL_ENTRY_IN', "
     "'DEAL_REASON_EXPERT', 1, 130000, -0.5, 0.256, 0, 0, 38001, 1762174800000, now())"),
    ("b3_positions", "INSERT INTO b3_positions (id, organization_id, account_hash, position_id, "
     "position_ticket, symbol, side, volume, price_open, state, attribution) VALUES (:id, :org, "
     ":acc, 88, 9001, 'WINZ26', 'buy', 1, 130000, 'unprotected', 'attributed')"),
    ("b3_exit_intents", "INSERT INTO b3_exit_intents (id, organization_id, account_hash, "
     "position_id, exit_reason, exit_due_at, started_at, deadline_at) VALUES (:id, :org, :acc, 88, "
     "'session_flatten', now(), now(), now() + interval '120 seconds')"),
    ("b3_bracket_learning", "INSERT INTO b3_bracket_learning (id, organization_id, account_hash, "
     "session_date, symbol, k) VALUES (:id, :org, :acc, current_date, 'WINZ26', 1)"),
    ("b3_reconciliations", "INSERT INTO b3_reconciliations (id, organization_id, account_hash, "
     "instance_id, reconciled_at, clean, consistent_passes, divergences) VALUES (:id, :org, :acc, "
     ":inst, now(), false, 0, '[\"volume\"]')"),
    ("b3_session_anchors", "INSERT INTO b3_session_anchors (id, organization_id, account_hash, "
     "session_date, anchor_equity, anchor_at) VALUES (:id, :org, :acc, current_date, 10000, now())"),
    ("b3_kill_switch_transitions", "INSERT INTO b3_kill_switch_transitions (id, organization_id, "
     "account_hash, from_state, to_state, from_causes, causes_after, reason, actor_type) VALUES "
     "(:id, :org, :acc, 'ACTIVE', 'WARNING', '{}', '{}', 'warning fraction', 'robot')"),
)  # fmt: skip
"""One row in every table ``make_world``/``propose`` do not reach, so isolation is proved
against data, never against an empty table."""


async def populate_all(engine: AsyncEngine, w: World) -> None:
    proposal = await propose(engine, w)
    async with as_app(engine, w.org) as c:
        epoch = None
        for table, sql in _POPULATE:
            row = uuid.uuid4()
            await c.execute(text(sql), w.params(id=row))
            epoch = row if table == "b3_management_epochs" else epoch
            if table not in ("b3_robot_heartbeats", "b3_robot_events"):
                await audit(c, w.org, (table, row))
        await c.execute(
            text("UPDATE b3_robot_accounts SET kill_state = 'WARNING' WHERE id = :a"),
            {"a": w.account_id},
        )
        order, request = uuid.uuid4(), uuid.uuid4()
        await c.execute(
            text(
                "INSERT INTO b3_orders (id, organization_id, account_hash, proposal_id, ticket, "
                "symbol, side, order_type, volume_initial, volume_current, magic, state, "
                "observed_at) VALUES (:id, :org, :acc, :prop, 9000, 'WINZ26', 'buy', "
                "'ORDER_TYPE_BUY_LIMIT', 1, 0, 38001, 'ORDER_STATE_FILLED', now())"
            ),
            w.params(id=order, prop=proposal),
        )
        await c.execute(
            text(
                "INSERT INTO b3_sltp_requests (sltp_request_id, organization_id, account_hash, "
                "position_id, epoch_id, request_position_ticket, sl, tp, purpose, built_at) "
                "VALUES (:id, :org, :acc, 88, :epoch, 9001, 129350, 0, 'repair', now())"
            ),
            w.params(id=request, epoch=epoch),
        )
        await audit(
            c, w.org, ("b3_robot_accounts", w.account_id), ("b3_orders", order),
            ("b3_sltp_requests", request),
        )  # fmt: skip


# --------------------------------------------------------------------------- catalogue


async def test_the_catalogue_is_24_forced_tenant_tables_matching_the_models(
    engine: AsyncEngine,
) -> None:
    assert len(TABLES) == 24
    assert set(TABLES) == {t for t in tenant_tables() if t.startswith("b3_")}
    async with engine.connect() as c:
        rows = (
            await c.execute(
                text(
                    "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, "
                    "(SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid "
                    " AND p.polname = 'tenant_isolation'), "
                    "(SELECT a.attnotnull FROM pg_attribute a WHERE a.attrelid = c.oid "
                    " AND a.attname = 'organization_id') "
                    "FROM pg_class c WHERE c.relname LIKE 'b3\\_%' AND c.relkind = 'r'"
                )
            )
        ).all()
    assert {r[0] for r in rows} == set(TABLES)
    assert all(r[1] and r[2] and r[3] == 1 and r[4] for r in rows), rows


async def test_enums_are_the_contracts_labels_verbatim(engine: AsyncEngine) -> None:
    async with engine.connect() as c:
        rows = (
            await c.execute(
                text(
                    "SELECT t.typname, array_agg(e.enumlabel ORDER BY e.enumsortorder) "
                    "FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid "
                    "WHERE t.typname LIKE 'b3\\_%' GROUP BY t.typname"
                )
            )
        ).all()
    actual = {name: list(labels) for name, labels in rows}
    assert actual == {k: [m.value for m in v] for k, v in B3_ENUMS.items()}
    assert actual == {k: list(v) for k, v in migration_ddl("enums").B3_ENUMS.items()}
    assert "b3_kill_state" not in actual  # "mesmo enum do SPOT": kill_switch_state


async def test_money_is_numeric_28_10_time_is_timestamptz_indexes_lead_with_org(
    engine: AsyncEngine,
) -> None:
    async with engine.connect() as c:
        numeric = (
            await c.execute(
                text(
                    "SELECT table_name, column_name, numeric_precision, numeric_scale "
                    "FROM information_schema.columns WHERE table_name LIKE 'b3\\_%' "
                    "AND data_type = 'numeric'"
                )
            )
        ).all()
        naive = await c.scalar(
            text(
                "SELECT count(*) FROM information_schema.columns WHERE table_name LIKE 'b3\\_%' "
                "AND data_type IN ('timestamp without time zone', 'real', 'double precision')"
            )
        )
        leads = (
            await c.execute(
                text(
                    "SELECT i.indexrelid::regclass::text, a.attname FROM pg_index i "
                    "JOIN pg_class t ON t.oid = i.indrelid "
                    "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = i.indkey[0] "
                    "WHERE t.relname LIKE 'b3\\_%'"
                )
            )
        ).all()
    assert numeric and all((r[2], r[3]) == (28, 10) for r in numeric), numeric
    assert naive == 0
    stray = {name for name, lead in leads if lead != "organization_id"}
    allowed = {f"pk_{t}" for t in TABLES} | {
        "uq_b3_entry_intents_client_order_id",
        "uq_b3_robot_authority_authority_id",
    }
    assert stray <= allowed, stray - allowed


async def test_no_role_may_delete_append_only_never_updates_config_only_retires(
    engine: AsyncEngine,
) -> None:
    async with engine.connect() as c:
        rows = (
            await c.execute(
                text(
                    "SELECT table_name, grantee, privilege_type FROM information_schema."
                    "role_table_grants WHERE table_name LIKE 'b3\\_%' "
                    "AND grantee IN ('hunter_app', 'hunter_worker')"
                )
            )
        ).all()
        columns = (
            await c.execute(
                text(
                    "SELECT table_name, column_name FROM information_schema.column_privileges "
                    "WHERE table_name LIKE 'b3\\_%' AND grantee = 'hunter_app' "
                    "AND privilege_type = 'UPDATE'"
                )
            )
        ).all()
    grants = {(t, g, p) for t, g, p in rows}
    assert not {g for g in grants if g[2] in ("DELETE", "TRUNCATE")}
    assert {(t, p) for t, g, p in grants if g == "hunter_worker"} == {(t, "SELECT") for t in TABLES}
    for table in DDL.B3_APP_APPEND_TABLES:
        assert {p for t, g, p in grants if t == table and g == "hunter_app"} == {"SELECT", "INSERT"}
    for table, column in DDL.B3_APP_CONFIG_TABLES.items():
        assert {c for t, c in columns if t == table} == {column}


# --------------------------------------------------------------------------- isolation


async def test_org_b_cannot_read_or_write_org_a_in_any_b3_table(engine: AsyncEngine) -> None:
    a, b = await make_world(engine), await make_world(engine)
    await populate_all(engine, a)
    async with as_app(engine, a.org) as c:
        seen_by_a = {t: await c.scalar(text(f"SELECT count(*) FROM {t}")) for t in TABLES}  # noqa: S608
    async with as_app(engine, b.org) as c:
        leaked: dict[str, int] = {}
        for t in TABLES:
            count_a = f"SELECT count(*) FROM {t} WHERE organization_id = :a"  # noqa: S608
            leaked[t] = await c.scalar(text(count_a), {"a": a.org})
    async with as_app(engine, None) as c:
        anonymous = {t: await c.scalar(text(f"SELECT count(*) FROM {t}")) for t in TABLES}  # noqa: S608
    assert all(n > 0 for n in seen_by_a.values()), seen_by_a  # every table holds A's data
    assert set(leaked.values()) == {0}, leaked
    assert set(anonymous.values()) == {0}, anonymous
    with pytest.raises(DBAPIError, match="row-level security"):
        async with as_app(engine, b.org) as c:
            await c.execute(
                text(
                    "INSERT INTO b3_holidays (id, organization_id, holiday_date, source_note) "
                    "VALUES (:id, :a, '2026-11-20', 'B3 calendar')"
                ),
                {"id": uuid.uuid4(), "a": a.org},
            )


# --------------------------------------------------------------------------- audit, append-only


async def test_a_mutation_without_its_audit_row_of_this_transaction_is_refused(
    engine: AsyncEngine,
) -> None:
    w = await make_world(engine)
    holiday = uuid.uuid4()
    insert = text(
        "INSERT INTO b3_holidays (id, organization_id, holiday_date, source_note) "
        "VALUES (:id, :org, '2026-12-25', 'B3 calendar 2026')"
    )
    with pytest.raises(DBAPIError, match="without an audit_logs row"):
        async with as_app(engine, w.org) as c:
            await c.execute(insert, {"id": holiday, "org": w.org})
    async with as_app(engine, w.org) as c:
        await audit(c, w.org, ("b3_holidays", holiday))  # an audit of an earlier transaction ...
    with pytest.raises(DBAPIError, match="without an audit_logs row"):
        async with as_app(engine, w.org) as c:  # ... does not cover this one
            await c.execute(insert, {"id": holiday, "org": w.org})
    async with as_app(engine, w.org) as c:
        await c.execute(insert, {"id": holiday, "org": w.org})
        await audit(c, w.org, ("b3_holidays", holiday))


async def test_append_only_rows_are_never_updated_deleted_or_truncated(engine: AsyncEngine) -> None:
    w = await make_world(engine)
    for statement in (
        "UPDATE b3_robot_instances SET started_at = now() WHERE instance_id = :inst",
        "DELETE FROM b3_robot_instances WHERE instance_id = :inst",
        "DELETE FROM b3_robot_authority WHERE id = :auth_row",
        "TRUNCATE b3_deals",
    ):
        with pytest.raises(DBAPIError, match="append-only|never deleted"):
            async with engine.begin() as c:  # as the owner: the guard holds it too
                await c.execute(text(statement), w.params())


# --------------------------------------------------------------------------- config


async def test_limits_are_versioned_contiguous_retire_only_and_never_a_json_number(
    engine: AsyncEngine,
) -> None:
    w = await make_world(engine)
    v2 = uuid.uuid4()
    insert = text(
        "INSERT INTO b3_risk_profiles (id, organization_id, limits_version, limits) "
        "VALUES (:id, :org, :v, CAST(:limits AS jsonb))"
    )
    for version, limits, match in (
        (3, '{"a": "1"}', "next version is 2"),
        (2, '{"daily_loss_limit_brl": 9000}', "limits_has_no_json_number"),
        (2, '{"a": "1"}', "uq_b3_risk_profiles_current"),  # v1 still current
    ):
        with pytest.raises(DBAPIError, match=match):
            async with as_app(engine, w.org) as c:
                await c.execute(insert, {"id": v2, "org": w.org, "v": version, "limits": limits})
                await audit(c, w.org, ("b3_risk_profiles", v2))
    with pytest.raises(DBAPIError, match="permission denied"):
        async with as_app(engine, w.org) as c:
            await c.execute(
                text("UPDATE b3_risk_profiles SET limits = '{}' WHERE id = :p"), {"p": w.profile}
            )
    async with as_app(engine, w.org) as c:
        await c.execute(
            text("UPDATE b3_risk_profiles SET superseded_at = now() WHERE id = :p"),
            {"p": w.profile},
        )
        await c.execute(insert, {"id": v2, "org": w.org, "v": 2, "limits": '{"a": {"b": "2"}}'})
        await audit(c, w.org, ("b3_risk_profiles", w.profile), ("b3_risk_profiles", v2))
    with pytest.raises(DBAPIError, match="already retired"):
        async with as_app(engine, w.org) as c:
            await c.execute(
                text("UPDATE b3_risk_profiles SET superseded_at = now() WHERE id = :p"),
                {"p": w.profile},
            )


async def test_two_current_grids_of_a_root_never_overlap_but_a_special_day_may(
    engine: AsyncEngine,
) -> None:
    w = await make_world(engine)
    insert = text(
        "INSERT INTO b3_session_grids (id, organization_id, symbol_root, grid_version, valid_from, "
        "valid_until, special_day, open_local, close_local, session_end_local, source_note) "
        "VALUES (:id, :org, 'WIN', :v, CAST(:f AS date), CAST(:u AS date), :s, '09:00', '18:25', "
        "'18:30', 'OC 050/2026-VNC')"
    )
    rows = (
        (1, "2026-11-03", None, False, None),
        (2, "2026-12-01", None, False, "overlap"),
        (2, "2026-11-20", "2026-11-20", True, None),
    )
    for version, start, until, special, refusal in rows:
        grid = uuid.uuid4()
        params = {
            "id": grid, "org": w.org, "v": version, "s": special,
            "f": date.fromisoformat(start), "u": until and date.fromisoformat(until),
        }  # fmt: skip
        if refusal is None:
            async with as_app(engine, w.org) as c:
                await c.execute(insert, params)
                await audit(c, w.org, ("b3_session_grids", grid))
            continue
        with pytest.raises(DBAPIError, match=refusal):
            async with as_app(engine, w.org) as c:
                await c.execute(insert, params)
                await audit(c, w.org, ("b3_session_grids", grid))


# --------------------------------------------------------------------------- machine A


async def test_one_grant_per_account_token_plus_one_db_clock_and_no_renewal(
    engine: AsyncEngine,
) -> None:
    w = await make_world(engine)
    assert await scalar(
        engine,
        "SELECT granted_at > '2026-01-01' FROM b3_robot_authority WHERE id = :i",
        {"i": w.authority_row},
    )
    regrant = text(
        "UPDATE b3_robot_authority SET authority_id = :new, fencing_token = :tok, status = "
        "'active', revoked_at = NULL WHERE id = :auth_row"
    )
    with pytest.raises(DBAPIError, match="previous grant is still active"):
        async with as_app(engine, w.org) as c:
            await c.execute(regrant, w.params(new=uuid.uuid4(), tok=2))
    with pytest.raises(DBAPIError, match="never renewed"):
        async with as_app(engine, w.org) as c:
            await c.execute(
                text(
                    "UPDATE b3_robot_authority SET authority_expires_at = authority_expires_at + interval '1 hour' WHERE id = :auth_row"
                ),
                w.params(),
            )
    async with as_app(engine, w.org) as c:
        await c.execute(
            text(
                "UPDATE b3_robot_authority SET status = 'revoked', revoked_at = now() WHERE id = :auth_row"
            ),
            w.params(),
        )
        await audit(c, w.org, ("b3_robot_authority", w.authority_row))
    with pytest.raises(DBAPIError, match="fencing_token \\+ 1"):
        async with as_app(engine, w.org) as c:
            await c.execute(regrant, w.params(new=uuid.uuid4(), tok=3))
    async with as_app(engine, w.org) as c:
        await c.execute(regrant, w.params(new=uuid.uuid4(), tok=2))
        await audit(c, w.org, ("b3_robot_authority", w.authority_row))
    with pytest.raises(DBAPIError, match="limits_version 7"):
        await arm(engine, w, limits_version=7)


# --------------------------------------------------------------------------- machine B and the claim


async def test_client_order_id_is_the_contract_formula_computed_by_the_database(
    engine: AsyncEngine,
) -> None:
    w = await make_world(engine)
    proposal = await propose(engine, w, approve=False)
    stored = await scalar(
        engine,
        "SELECT client_order_id FROM b3_entry_intents WHERE proposal_id = :p",
        {"p": proposal},
    )
    assert stored == client_order_id(proposal) and len(stored) == 18
    for sample in (
        uuid.UUID(int=0),
        uuid.UUID("01994d00-6c1a-7000-8000-000000000022"),
        uuid.uuid4(),
    ):
        assert await scalar(
            engine, "SELECT b3_client_order_id(:u)", {"u": sample}
        ) == client_order_id(sample)
    with pytest.raises(DBAPIError, match="can only be updated to DEFAULT|generated column"):
        async with as_app(engine, w.org) as c:
            await c.execute(
                text("UPDATE b3_entry_intents SET client_order_id = 'HBX' WHERE proposal_id = :p"),
                {"p": proposal},
            )


async def test_intent_transitions_terminals_and_the_30_second_approval(engine: AsyncEngine) -> None:
    w = await make_world(engine)
    proposal = await propose(engine, w, approve=False)
    with pytest.raises(DBAPIError, match="approval_lives_30_seconds"):
        async with as_app(engine, w.org) as c:
            await c.execute(
                text(
                    "UPDATE b3_entry_intents SET status = 'approved', decision = '{}', decided_at = now(), "
                    "approved_at = now(), expires_at = now() + interval '31 seconds', limits_version = 1, "
                    "grid_version = 1, spec_pin_id = :pin, n_final = 1, limit_price = 1 WHERE proposal_id = :prop"
                ),
                w.params(prop=proposal),
            )
    stamped = (
        "CAST(:dec AS jsonb) || jsonb_build_object('as_of', now(), 'approved_at', now(), "
        "'expires_at', now() + interval '30 seconds')"
    )
    no_sizing = json.loads(decision_json(proposal, w))
    del no_sizing["sizing"]
    for decision_sql, decision, limit_price in (
        (stamped, decision_json(proposal, w), "130010"),  # sizing disagrees with the column
        ("CAST(:dec AS jsonb)", decision_json(proposal, w), "130005"),  # a late write re-dates it
        (stamped, json.dumps(no_sizing), "130005"),  # no sizing at all: NULL must not pass
    ):
        with pytest.raises(DBAPIError, match="decision_matches_its_columns"):
            async with as_app(engine, w.org) as c:
                await c.execute(
                    text(_APPROVE_WITH.replace("{decision}", decision_sql)),
                    w.params(prop=proposal, dec=decision, lp=limit_price),
                )
    for status, match in (
        ("submitting", "claimed_iff_post_claim|not a transition"),
        ("filled", "not a transition"),
    ):
        with pytest.raises(DBAPIError, match=match):
            async with as_app(engine, w.org) as c:
                await c.execute(
                    text(
                        "UPDATE b3_entry_intents SET status = CAST(:s AS b3_entry_intent_status) WHERE proposal_id = :p"
                    ),
                    {"s": status, "p": proposal},
                )
    async with as_app(engine, w.org) as c:
        await c.execute(
            text(
                "UPDATE b3_entry_intents SET status = 'expired', terminal_reason = 'instance_gone' WHERE proposal_id = :p"
            ),
            {"p": proposal},
        )
        await audit(c, w.org, ("b3_entry_intents", proposal))
    with pytest.raises(DBAPIError, match="expired is terminal"):
        async with as_app(engine, w.org) as c:
            await c.execute(
                text("UPDATE b3_entry_intents SET terminal_reason = 'x' WHERE proposal_id = :p"),
                {"p": proposal},
            )


async def test_the_claim_needs_this_instance_token_entries_fresh_approval_and_same_limits(
    engine: AsyncEngine,
) -> None:
    w = await make_world(engine)
    proposal = await propose(engine, w)
    with pytest.raises(DBAPIError, match="not_armed"):
        await claim(engine, w, proposal)
    await arm(engine, w)
    with pytest.raises(DBAPIError, match="authority_mismatch"):
        await claim(engine, w, proposal, token=9)
    stale = await propose(engine, w, age_s=40)
    with pytest.raises(DBAPIError, match="approval_expired"):
        await claim(engine, w, stale)
    assert await claim(engine, w, proposal) == 1
    row = await scalar(
        engine,
        "SELECT status::text || '|' || (claimed_at <= clock_timestamp())::text || '|' || "
        "(claimed_at > now() - interval '1 minute')::text FROM b3_entry_intents WHERE proposal_id = :p",
        {"p": proposal},
    )
    assert row == "submitting|true|true"
    assert (
        await claim(engine, w, proposal) == 0
    )  # a repeat changes nothing; the API reads the claim back
    with pytest.raises(DBAPIError, match="not a transition"):
        async with as_app(engine, w.org) as c:  # never re-sent (I-E-2)
            await c.execute(
                text(
                    "UPDATE b3_entry_intents SET status = 'unknown', unknown_cause = 'process_died' WHERE proposal_id = :p"
                ),
                {"p": proposal},
            )
            await c.execute(
                text("UPDATE b3_entry_intents SET status = 'approved' WHERE proposal_id = :p"),
                {"p": proposal},
            )
    later = await propose(engine, w)
    async with as_app(engine, w.org) as c:
        new_profile = uuid.uuid4()
        await c.execute(
            text("UPDATE b3_risk_profiles SET superseded_at = now() WHERE id = :p"),
            {"p": w.profile},
        )
        await c.execute(
            text(
                """INSERT INTO b3_risk_profiles (id, organization_id, limits_version, limits) VALUES (:id, :org, 2, '{"a": "1"}')"""
            ),
            {"id": new_profile, "org": w.org},
        )
        await audit(c, w.org, ("b3_risk_profiles", w.profile), ("b3_risk_profiles", new_profile))
    with pytest.raises(DBAPIError, match="limits_changed"):
        await claim(engine, w, later)


async def test_two_executors_claim_the_same_intent_and_exactly_one_wins(
    engine: AsyncEngine,
) -> None:
    w = await make_world(engine)
    await arm(engine, w)
    proposal = await propose(engine, w)
    other = async_engine(engine.url.render_as_string(hide_password=False))
    try:
        async with as_app(engine, w.org) as first:
            assert (await first.execute(_CLAIM, w.params(prop=proposal, tok=1))).rowcount == 1
            second = asyncio.create_task(claim(other, w, proposal))
            await asyncio.sleep(0.5)
            assert not second.done(), "the second executor must wait on the first"
            await audit(first, w.org, ("b3_entry_intents", proposal))
        assert await second == 0
    finally:
        await other.dispose()


async def test_a_claim_waiting_on_a_revocation_loses_once_it_commits(engine: AsyncEngine) -> None:
    w = await make_world(engine)
    await arm(engine, w)
    proposal = await propose(engine, w)
    other = async_engine(engine.url.render_as_string(hide_password=False))
    try:
        async with as_app(engine, w.org) as revoke:
            await revoke.execute(
                text(
                    "UPDATE b3_robot_authority SET status = 'revoked', revoked_at = now() "
                    "WHERE id = :auth_row"
                ),
                w.params(),
            )
            waiting = asyncio.create_task(claim(other, w, proposal))
            await asyncio.sleep(0.5)
            assert not waiting.done(), "the claim must wait on the robot account lock"
            await audit(revoke, w.org, ("b3_robot_authority", w.authority_row))
        with pytest.raises(DBAPIError, match="authority_mismatch"):
            await waiting
    finally:
        await other.dispose()


# --------------------------------------------------------------------------- kill switch


async def test_the_robot_kill_switch_moves_only_with_its_transition_and_owner_rules(
    engine: AsyncEngine,
) -> None:
    w = await make_world(engine)
    move = text(
        "UPDATE b3_robot_accounts SET kill_state = CAST(:to AS kill_switch_state), "
        "active_causes = CAST(CAST(:after AS text[]) AS b3_kill_cause[]) WHERE id = :acc_id"
    )
    transition = text(
        "INSERT INTO b3_kill_switch_transitions (id, organization_id, account_hash, from_state, "
        "to_state, from_causes, causes_after, cause, reason, actor_type) VALUES (:id, :org, :acc, "
        "CAST(:frm AS kill_switch_state), CAST(:to AS kill_switch_state), CAST(CAST(:before AS text[]) AS "
        "b3_kill_cause[]), CAST(CAST(:after AS text[]) AS b3_kill_cause[]), CAST(:cause AS b3_kill_cause), 'test', :actor)"
    )

    async def step(
        frm: str,
        to: str,
        before: list[str],
        after: list[str],
        cause: str,
        actor: str,
        *,
        with_row: bool = True,
    ) -> None:
        tid = uuid.uuid4()
        params = w.params(
            id=tid,
            acc_id=w.account_id,
            frm=frm,
            to=to,
            before=before,
            after=after,
            cause=cause,
            actor=actor,
        )
        async with as_app(engine, w.org) as c:
            await c.execute(move, params)
            audits = [("b3_robot_accounts", w.account_id)]
            if with_row:
                await c.execute(transition, params)
                audits.append(("b3_kill_switch_transitions", tid))
            await audit(c, w.org, *audits)

    with pytest.raises(DBAPIError, match="without its transition"):
        await step(
            "ACTIVE",
            "TRADING_DISABLED",
            [],
            ["broker_reject_breaker"],
            "broker_reject_breaker",
            "robot",
            with_row=False,
        )
    await step(
        "ACTIVE",
        "TRADING_DISABLED",
        [],
        ["broker_reject_breaker"],
        "broker_reject_breaker",
        "robot",
    )
    await step(
        "TRADING_DISABLED",
        "TRADING_DISABLED",
        ["broker_reject_breaker"],
        ["broker_reject_breaker", "daily_loss_limit"],
        "daily_loss_limit",
        "robot",
    )
    with pytest.raises(
        DBAPIError, match="only_the_owner_releases_a_latch"
    ):  # the turnover may not take the breaker with it
        await step(
            "TRADING_DISABLED",
            "ACTIVE",
            ["broker_reject_breaker", "daily_loss_limit"],
            [],
            "daily_loss_limit",
            "robot",
        )
    await step(
        "TRADING_DISABLED",
        "TRADING_DISABLED",
        ["broker_reject_breaker", "daily_loss_limit"],
        ["broker_reject_breaker"],
        "daily_loss_limit",
        "robot",
    )
    with pytest.raises(DBAPIError, match="an_agent_only_disables"):
        await step(
            "TRADING_DISABLED",
            "EMERGENCY",
            ["broker_reject_breaker"],
            ["broker_reject_breaker", "owner_command"],
            "owner_command",
            "agent",
        )
    await step(
        "TRADING_DISABLED",
        "EMERGENCY",
        ["broker_reject_breaker"],
        ["broker_reject_breaker", "owner_button"],
        "owner_button",
        "user",
    )
    with pytest.raises(DBAPIError, match="only_the_owner_leaves_emergency"):
        await step(
            "EMERGENCY",
            "TRADING_DISABLED",
            ["broker_reject_breaker", "owner_button"],
            ["broker_reject_breaker"],
            "owner_button",
            "robot",
        )


# --------------------------------------------------------------------------- machine C and the slot


async def test_positions_exit_only_to_closed_and_the_slot_waits_for_its_request(
    engine: AsyncEngine,
) -> None:
    w = await make_world(engine)
    pos, epoch, req, req2, exit_id = (uuid.uuid4() for _ in range(5))
    p = w.params(pos=pos, epoch=epoch, req=req, req2=req2, exit=exit_id)
    request = text(
        "INSERT INTO b3_sltp_requests (sltp_request_id, organization_id, account_hash, position_id, "
        "epoch_id, request_position_ticket, sl, tp, purpose, built_at) VALUES (CAST(:rid AS uuid), :org, "
        ":acc, 77, :epoch, 501, CAST(:sl AS numeric), 0, 'repair', now())"
    )

    async def write(sql: Any, *audits: tuple[str, Any], **extra: Any) -> None:
        async with as_app(engine, w.org) as c:
            await c.execute(text(sql) if isinstance(sql, str) else sql, {**p, **extra})
            await audit(c, w.org, *audits)

    await write(
        "INSERT INTO b3_positions (id, organization_id, account_hash, position_id, position_ticket, "
        "symbol, side, volume, price_open, state, attribution, sl_confirmed) VALUES (:pos, :org, :acc, "
        "77, 501, 'WINZ26', 'buy', 1, 130000, 'protected', 'attributed', 129350)",
        ("b3_positions", pos),
    )
    await write(
        "INSERT INTO b3_management_epochs (epoch_id, organization_id, account_hash, instance_id, "
        "authority_id, host_hash) VALUES (:epoch, :org, :acc, :inst, :auth, :host)",
        ("b3_management_epochs", epoch),
    )
    with pytest.raises(DBAPIError, match="without its b3_exit_intents row"):
        await write(
            "UPDATE b3_positions SET state = 'exiting', exit_reason = 'time_exit' WHERE id = :pos",
            ("b3_positions", pos),
        )
    other_account = _hex(uuid.uuid4(), "account")
    other_epoch = uuid.uuid4()
    async with engine.begin() as c:  # a second account of the same organization
        await c.execute(
            text(
                "INSERT INTO b3_robot_accounts (id, organization_id, registered_account_hash, "
                "authorized_host_hash) VALUES (:id, :org, :other, :host)"
            ),
            w.params(id=other_epoch, other=other_account),
        )
        await c.execute(
            text(
                "INSERT INTO b3_management_epochs (epoch_id, organization_id, account_hash, "
                "instance_id, authority_id, host_hash) VALUES (:e, :org, :other, :inst, :auth, :host)"
            ),
            w.params(e=other_epoch, other=other_account),
        )
        await audit(
            c, w.org, ("b3_robot_accounts", other_epoch), ("b3_management_epochs", other_epoch)
        )
    with pytest.raises(
        DBAPIError, match="fk_b3_sltp_requests_organization_id_b3_management_epochs"
    ):
        await write(
            request, ("b3_sltp_requests", req), rid=str(req), sl="129400", epoch=other_epoch
        )
    with pytest.raises(DBAPIError, match="never_without_a_stop"):
        await write(request, ("b3_sltp_requests", req), rid=str(req), sl="0")
    await write(request, ("b3_sltp_requests", req), rid=str(req), sl="129400")
    with pytest.raises(DBAPIError, match="uq_b3_sltp_requests_one_in_flight"):
        await write(request, ("b3_sltp_requests", req2), rid=str(req2), sl="129450")
    await write(
        "UPDATE b3_sltp_requests SET status = 'unknown' WHERE sltp_request_id = :req",
        ("b3_sltp_requests", req),
    )
    await write(
        "UPDATE b3_positions SET sltp_slot = 'unknown' WHERE id = :pos", ("b3_positions", pos)
    )
    with pytest.raises(DBAPIError, match="I-SL-3"):
        await write(
            "UPDATE b3_positions SET sltp_slot = 'idle' WHERE id = :pos", ("b3_positions", pos)
        )
    with pytest.raises(DBAPIError, match="downgrade"):
        await write(
            "UPDATE b3_sltp_requests SET status = 'intended' WHERE sltp_request_id = :req",
            ("b3_sltp_requests", req),
        )
    with pytest.raises(DBAPIError, match="manual_resolution_carries_the_journal_line"):
        await write(
            "UPDATE b3_sltp_requests SET status = 'resolved_manual', resolved_at = now(), "
            "resolved_by = :inst WHERE sltp_request_id = :req",
            ("b3_sltp_requests", req),
        )
    await write(
        "UPDATE b3_sltp_requests SET status = 'done' WHERE sltp_request_id = :req",
        ("b3_sltp_requests", req),
    )
    await write("UPDATE b3_positions SET sltp_slot = 'idle' WHERE id = :pos", ("b3_positions", pos))
    await write(
        "INSERT INTO b3_exit_intents (id, organization_id, account_hash, position_id, exit_reason, "
        "exit_due_at, started_at, deadline_at) VALUES (:exit, :org, :acc, 77, 'time_exit', now(), "
        "now(), now() + interval '120 seconds')",
        ("b3_exit_intents", exit_id),
    )
    await write(
        "UPDATE b3_positions SET state = 'exiting', exit_reason = 'time_exit' WHERE id = :pos",
        ("b3_positions", pos),
    )
    with pytest.raises(DBAPIError, match="I-X-3"):
        await write(
            "UPDATE b3_positions SET state = 'protected' WHERE id = :pos", ("b3_positions", pos)
        )
    with pytest.raises(DBAPIError, match="only a reversal"):
        await write(
            "UPDATE b3_positions SET exit_reason = 'emergency' WHERE id = :pos",
            ("b3_positions", pos),
        )
    await write(
        "UPDATE b3_positions SET exit_reason = 'reversal' WHERE id = :pos", ("b3_positions", pos)
    )
    await write(
        "UPDATE b3_positions SET state = 'closed', volume = 0, close_cause = 'bracket_tp', closed_at = now() WHERE id = :pos",
        ("b3_positions", pos),
    )
    with pytest.raises(DBAPIError, match="closed is terminal"):
        await write("UPDATE b3_positions SET volume = 1 WHERE id = :pos", ("b3_positions", pos))
    # journal_lost after the close: the slot of a closed position may still become unknown
    await write(
        "UPDATE b3_positions SET sltp_slot = 'unknown' WHERE id = :pos", ("b3_positions", pos)
    )


# --------------------------------------------------------------------------- downgrade, check


def test_the_downgrade_refuses_while_a_b3_row_exists(upgraded: str) -> None:
    async def seed() -> None:
        created = async_engine(upgraded)
        try:
            await make_world(created)
        finally:
            await created.dispose()

    asyncio.run(seed())
    with pytest.raises(Exception, match="cannot be reversed"):
        command.downgrade(alembic_config(upgraded), PREVIOUS)


def test_the_revision_round_trips_clean_and_alembic_check_holds(container_url: str) -> None:
    url = asyncio.run(create_database(container_url, "hunter_schema_b3_roundtrip"))
    config = alembic_config(url)
    command.upgrade(config, REVISION)
    command.downgrade(config, PREVIOUS)
    command.upgrade(config, REVISION)
    if len(ScriptDirectory.from_config(config).get_heads()) != 1:
        pytest.skip(
            "two heads in this tree (the held 0070); alembic check runs on a single-head copy"
        )
    command.check(config)
