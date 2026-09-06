"""``infra/scripts/recompute_funding.py`` against a real Postgres — S2-funding.

Loaded by path: the script is not an installed package, same convention as
``infra/scripts/tests/test_create_partitions.py`` and
``packages/core/tests/integration/test_schema_seed_and_partitions.py``.

The terminal outcome here is written directly by SQL, not produced by walking
bars through :func:`hunter_strategy_worker.consumer.sweep_outcomes` — this
suite is about the recompute script's own read/write/idempotency contract, not
about re-proving the outcome engine (that is ``test_shadow_outcomes.py``'s
job). It borrows the ``tracked`` fixture only for a valid market and a real
``agent_signals`` row to hang a ``signal_outcomes`` row off of.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session

from .test_shadow_outcomes import tracked  # noqa: F401  # pyright: ignore[reportUnusedImport]

pytestmark = pytest.mark.integration

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "infra" / "scripts" / "recompute_funding.py"
T0 = datetime(2026, 9, 6, 0, 0, tzinfo=UTC)

_ASSUMED_COSTS = {
    "spread_bps": "2",
    "slippage_bps": "5",
    "fee_bps": "4",
    "max_entry_delay_s": "120",
}


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("hunter_infra_recompute_funding_it", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses' own string-annotation resolution (from __future__ import
    # annotations, used by the script) looks the module up in sys.modules by
    # name while its own body is still executing.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


async def _signal_id(ctx: dict[str, Any]) -> Any:
    async with role_session(ctx["factory"], db_role="hunter_worker") as session:
        row = (await session.execute(text("SELECT id FROM agent_signals LIMIT 1"))).first()
    assert row is not None
    return row.id


async def _seed_h2_shaped_outcome(
    ctx: dict[str, Any], *, exit_at_open: bool = True, exit_bar_open: datetime | None = None
) -> Any:
    """A terminal outcome exactly like the H2 census: the schedule's nominal
    instant is ``T0 + 8h``, the real ``funding_rates`` row is 5 ms later, and
    the old exact-equality match left it ``funding_missing``."""
    signal_id = await _signal_id(ctx)
    entry_ts, exit_ts = T0, T0 + timedelta(hours=9)
    funding_meta: dict[str, Any] = {
        "per_unit": None,
        "reason": f"funding_missing:{(T0 + timedelta(hours=8)).isoformat()}",
        "settlements": 0,
        "interval_s": 28800,
        "notes": [],
        "charged_at": [],
    }
    meta: dict[str, Any] = {
        "assumed_costs": _ASSUMED_COSTS,
        "progress": {
            "exit_at_open": exit_at_open,
            "exit_bar_open": None if exit_bar_open is None else exit_bar_open.isoformat(),
        },
        "funding": funding_meta,
        "r_net_reason": funding_meta["reason"],
        "r_ex_funding": "0.5",
    }
    async with role_session(ctx["factory"], db_role="hunter_worker") as session:
        await session.execute(
            text(
                "UPDATE signal_outcomes SET tracking_state = 'terminal', result = 'target', "
                "virtual_entry = :ve, virtual_stop = :vs, entry_ts = :entry_ts, "
                "exit_price = :ep, exit_ts = :exit_ts, r_multiple = NULL, "
                "meta = CAST(:meta AS jsonb) "
                "WHERE signal_id = :signal_id"
            ),
            {
                "ve": Decimal("100"),
                "vs": Decimal("99"),
                "entry_ts": entry_ts,
                "ep": Decimal("101"),
                "exit_ts": exit_ts,
                "meta": _dump(meta),
                "signal_id": signal_id,
            },
        )
        await session.execute(
            text(
                "INSERT INTO funding_rates (market_id, funding_time, rate, mark_price) "
                "VALUES (:m, :t, :r, :p)"
            ),
            {
                "m": ctx["market_id"],
                "t": T0 - timedelta(hours=8),
                "r": Decimal("0.0001"),
                "p": Decimal("100"),
            },
        )
        await session.execute(
            text(
                "INSERT INTO funding_rates (market_id, funding_time, rate, mark_price) "
                "VALUES (:m, :t, :r, :p)"
            ),
            {"m": ctx["market_id"], "t": T0, "r": Decimal("0.0001"), "p": Decimal("100")},
        )
        await session.execute(
            text(
                "INSERT INTO funding_rates (market_id, funding_time, rate, mark_price) "
                "VALUES (:m, :t, :r, :p)"
            ),
            {
                "m": ctx["market_id"],
                "t": T0 + timedelta(hours=8, milliseconds=5),
                "r": Decimal("0.0002"),
                "p": Decimal("100"),
            },
        )
    return signal_id


def _dump(value: dict[str, Any]) -> str:
    return json.dumps(value)


class TestRecomputeFunding:
    async def test_a_resolvable_outcome_is_written_with_audit_and_is_idempotent(
        self,
        tracked: dict[str, Any],  # noqa: F811 (the fixture imported above)
    ) -> None:
        module = _load_module()
        signal_id = await _seed_h2_shaped_outcome(tracked)

        async with role_session(tracked["factory"], db_role="hunter_worker") as conn:
            candidates = await module._candidates(conn)
            assert len(candidates) == 1
            history = await module._funding_history(conn, candidates[0])
            result = module._recompute(candidates[0], history)
            assert result.r_multiple is not None
            wrote = await module._apply(conn, result, reason="test: H2 shape")
            assert wrote is True

        async with role_session(tracked["factory"], db_role="hunter_worker") as session:
            row = (
                await session.execute(
                    text("SELECT r_multiple, meta FROM signal_outcomes WHERE signal_id = :id"),
                    {"id": signal_id},
                )
            ).one()
        assert row.r_multiple is not None
        funding = row.meta["funding"]
        assert funding["reason"] is None  # never overwritten by the audit trail
        assert funding["previous"]["reason"].startswith("funding_missing")
        assert funding["recompute_reason"] == "test: H2 shape"
        assert "recomputed_at" in funding
        assert row.meta["r_net_reason"] is None

        # Idempotent: a second pass finds nothing left to do for this row.
        async with role_session(tracked["factory"], db_role="hunter_worker") as conn:
            second_pass = await module._candidates(conn)
        assert signal_id not in {c.signal_id for c in second_pass}

    async def test_apply_through_the_real_run_path_never_writes_an_unresolved_row(
        self,
        tracked: dict[str, Any],  # noqa: F811 (the fixture imported above)
    ) -> None:
        """The guard lives in ``_process`` (what ``_run`` calls), not in the
        caller: with ``--apply`` a row that still does not resolve must come
        out byte-identical — no ``recomputed_at``, no ``previous`` — and the
        counters must say so (code review of d878fd6, finding 2)."""
        module = _load_module()
        signal_id = await _signal_id(tracked)
        meta: dict[str, Any] = {
            "assumed_costs": _ASSUMED_COSTS,
            "progress": {"exit_at_open": True, "exit_bar_open": None},
            "funding": {
                "per_unit": None,
                "reason": "funding_schedule_unknown",
                "settlements": 0,
                "interval_s": None,
                "notes": [],
                "charged_at": [],
            },
            "r_net_reason": "funding_schedule_unknown",
            "r_ex_funding": "0.5",
        }
        async with role_session(tracked["factory"], db_role="hunter_worker") as session:
            await session.execute(
                text(
                    "UPDATE signal_outcomes SET tracking_state = 'terminal', result = 'target', "
                    "virtual_entry = :ve, virtual_stop = :vs, entry_ts = :entry_ts, "
                    "exit_price = :ep, exit_ts = :exit_ts, r_multiple = NULL, "
                    "meta = CAST(:meta AS jsonb) "
                    "WHERE signal_id = :signal_id"
                ),
                {
                    "ve": Decimal("100"),
                    "vs": Decimal("99"),
                    "entry_ts": T0,
                    "ep": Decimal("101"),
                    "exit_ts": T0 + timedelta(minutes=5),
                    "meta": _dump(meta),
                    "signal_id": signal_id,
                },
            )

        def open_tx() -> Any:
            return role_session(tracked["factory"], db_role="hunter_worker")

        total, resolved, applied = await module._process(open_tx, apply=True, reason="test: apply")
        assert (total, resolved, applied) == (1, 0, 0)

        async with role_session(tracked["factory"], db_role="hunter_worker") as session:
            row = (
                await session.execute(
                    text("SELECT r_multiple, meta FROM signal_outcomes WHERE signal_id = :id"),
                    {"id": signal_id},
                )
            ).one()
        assert row.r_multiple is None
        assert row.meta["funding"] == meta["funding"]  # untouched: no audit keys added
        assert row.meta["r_net_reason"] == "funding_schedule_unknown"

    async def test_a_still_unresolvable_outcome_is_reported_but_never_written(
        self,
        tracked: dict[str, Any],  # noqa: F811 (the fixture imported above)
    ) -> None:
        module = _load_module()
        signal_id = await _signal_id(tracked)
        meta: dict[str, Any] = {
            "assumed_costs": _ASSUMED_COSTS,
            "progress": {"exit_at_open": True, "exit_bar_open": None},
            "funding": {
                "per_unit": None,
                "reason": "funding_schedule_unknown",
                "settlements": 0,
                "interval_s": None,
                "notes": [],
                "charged_at": [],
            },
            "r_net_reason": "funding_schedule_unknown",
            "r_ex_funding": "0.5",
        }
        async with role_session(tracked["factory"], db_role="hunter_worker") as session:
            await session.execute(
                text(
                    "UPDATE signal_outcomes SET tracking_state = 'terminal', result = 'target', "
                    "virtual_entry = :ve, virtual_stop = :vs, entry_ts = :entry_ts, "
                    "exit_price = :ep, exit_ts = :exit_ts, r_multiple = NULL, "
                    "meta = CAST(:meta AS jsonb) "
                    "WHERE signal_id = :signal_id"
                ),
                {
                    "ve": Decimal("100"),
                    "vs": Decimal("99"),
                    "entry_ts": T0,
                    "ep": Decimal("101"),
                    "exit_ts": T0 + timedelta(minutes=5),
                    "meta": _dump(meta),
                    "signal_id": signal_id,
                },
            )

        async with role_session(tracked["factory"], db_role="hunter_worker") as conn:
            candidates = await module._candidates(conn)
            assert len(candidates) == 1
            history = await module._funding_history(conn, candidates[0])
            result = module._recompute(candidates[0], history)
        # Still unestablishable: _run() only calls _apply() when r_multiple is
        # not None, so this row is reported and never written — checked below.
        assert result.r_multiple is None

        async with role_session(tracked["factory"], db_role="hunter_worker") as session:
            row = (
                await session.execute(
                    text("SELECT r_multiple, meta FROM signal_outcomes WHERE signal_id = :id"),
                    {"id": signal_id},
                )
            ).one()
        assert row.r_multiple is None
        assert row.meta["funding"]["reason"] == "funding_schedule_unknown"
        assert "previous" not in row.meta["funding"]
