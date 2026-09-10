"""T3.69b — the wallet's limits come from its linked ``risk_profiles`` row, or nothing is admitted.

Until this task the engine applied ``hunter_risk.limits.PAPER_V1`` because
``admit`` defaults to it and ``admission_cycle`` never passed the argument: the
persisted row was the **declared** source and the constant the **applied** one
(RISK_ENGINE.md §2, note of T3.69). The resolver below closes that gap, and it
fails **closed**: a wallet with no linked profile, a row that does not validate
into :class:`~hunter_risk.limits.RiskLimits`, or a row that differs from the
constant field by field admits nothing, by name.

No database here — every case is the pure ``resolve_limits`` over the three
values one row carries, plus the gate's own dedupe over a labelled stub session
(CLAUDE.md: a double is labelled, never a silent mock of production behaviour).
The worker path against a real Postgres is
``tests/integration/paper/test_risk_profile_gate.py``.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

import pytest

from hunter_execution_worker.risk_profile import (
    DIVERGED,
    INVALID,
    LINKED,
    MISSING,
    RiskProfileGate,
    resolve_limits,
    wallet_limits,
)
from hunter_execution_worker.wallet import WalletRef
from hunter_risk.limits import PAPER_V1

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.unit

WALLET = WalletRef(uuid.UUID(int=1), uuid.UUID(int=2))
PROFILE_ID = uuid.UUID(int=3)
STORED = PAPER_V1.model_dump(mode="json")
"""Exactly what the seed writes (RISK_ENGINE.md §2): fractions as JSON strings."""


def _resolve(stored: object, *, profile_id: uuid.UUID | None = PROFILE_ID) -> Any:
    return resolve_limits(profile_id=profile_id, preset="paper_v1", stored=stored)


class TestTheLinkedRowIsTheAppliedSource:
    def test_a_seeded_row_resolves_to_the_engine_object(self) -> None:
        resolved = _resolve(STORED)
        assert resolved.state == LINKED
        assert resolved.limits == PAPER_V1
        assert resolved.usable

    def test_the_row_and_not_the_constant_is_what_the_caller_gets(self) -> None:
        # The identity that matters: the object handed to ``admit`` was built
        # from the row's own bytes, not taken from the module constant.
        limits = _resolve(STORED).limits
        assert limits is not PAPER_V1
        assert limits.risk_per_trade_pct == Decimal("0.0025")


class TestFailClosed:
    def test_a_wallet_with_no_linked_profile_admits_nothing(self) -> None:
        resolved = _resolve(None, profile_id=None)
        assert resolved.state == MISSING
        assert resolved.limits is None
        assert not resolved.usable

    def test_a_linked_row_whose_limits_are_null_is_missing_too(self) -> None:
        # ``risk_profile_id`` set and the join finding nothing (deleted row):
        # a dangling link is not a profile, and inventing one would be the
        # constant deciding again under another name.
        assert _resolve(None).state == MISSING

    def test_an_unknown_key_does_not_validate(self) -> None:
        # ``extra="forbid"``: the ten-error row of T3.1b (DATABASE.md §18.8).
        resolved = _resolve(STORED | {"auto_close_on_emergency": False})
        assert resolved.state == INVALID
        assert "auto_close_on_emergency" in resolved.detail

    def test_a_missing_key_does_not_validate(self) -> None:
        resolved = _resolve({key: value for key, value in STORED.items() if key != "max_leverage"})
        assert resolved.state == INVALID
        assert "max_leverage" in resolved.detail

    def test_a_fraction_stored_as_a_json_number_does_not_validate(self) -> None:
        # ``RiskModel._refuse_float``: ``Decimal(0.0025)`` is not
        # ``Decimal("0.0025")``, and a row re-typed by hand as JSON numbers is
        # exactly how that error would reach the sizing formula unnoticed.
        resolved = _resolve(STORED | {"risk_per_trade_pct": 0.0025})
        assert resolved.state == INVALID
        assert "float" in resolved.detail

    def test_a_widened_ceiling_is_refused_by_name(self) -> None:
        # A row edited to 1 % per trade is four times Everton's number; the
        # constant stays the guard, so this never becomes the applied limit.
        resolved = _resolve(STORED | {"risk_per_trade_pct": "0.01"})
        assert resolved.state == DIVERGED
        assert resolved.detail == "risk_per_trade_pct"
        assert resolved.limits is None

    def test_a_row_of_another_preset_is_refused(self) -> None:
        resolved = _resolve(
            STORED | {"profile": "balanced", "max_total_exposure_pct": "0.60"},
        )
        assert resolved.state == DIVERGED
        assert resolved.detail == "profile, max_total_exposure_pct"


class _Row:
    def __init__(self, profile_id: uuid.UUID | None, stored: object) -> None:
        self.profile_id = profile_id
        self.preset = None if profile_id is None else "paper_v1"
        self.limits = stored


class _Result:
    def __init__(self, row: _Row | None) -> None:
        self._row = row

    def first(self) -> _Row | None:
        return self._row


class _StubSession:
    """Labelled double: answers the one SELECT the resolver makes, nothing else."""

    def __init__(self, row: _Row | None) -> None:
        self.row = row
        self.queries = 0

    async def execute(self, *_args: object, **_kwargs: object) -> _Result:
        self.queries += 1
        return _Result(self.row)


class _Recorder:
    def __init__(self) -> None:
        self.lines: list[tuple[str, str]] = []

    def warning(self, event: str, **fields: object) -> None:
        self.lines.append((event, str(fields.get("reason", ""))))

    def info(self, event: str, **fields: object) -> None:
        self.lines.append((event, str(fields.get("reason", ""))))


async def _resolved_through(session: _StubSession) -> Any:
    return await wallet_limits(cast("AsyncSession", session), wallet=WALLET)


@pytest.mark.asyncio
class TestTheQueryAndTheGate:
    async def test_a_wallet_row_that_does_not_exist_is_missing(self) -> None:
        assert (await _resolved_through(_StubSession(None))).state == MISSING

    async def test_the_linked_row_is_read_back_whole(self) -> None:
        resolved = await _resolved_through(_StubSession(_Row(PROFILE_ID, STORED)))
        assert resolved.state == LINKED
        assert resolved.limits == PAPER_V1

    async def test_a_refusal_is_named_once_and_not_every_second(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The admission loop polls at 1 s: naming the same refusal every pass
        # writes 86.400 identical lines a day and buries the log (the doctrine
        # of ``admission_cycle.report_unreadable``).
        recorder = _Recorder()
        monkeypatch.setattr("hunter_execution_worker.risk_profile.logger", recorder)
        gate = RiskProfileGate()
        session = _StubSession(_Row(None, None))
        for _ in range(3):
            assert (await gate.resolve(cast("AsyncSession", session), wallet=WALLET)).limits is None
        assert [event for event, _ in recorder.lines] == ["admission_refused_no_risk_profile"]
        assert recorder.lines[0][1] == MISSING
        assert session.queries == 3

    async def test_the_link_being_made_is_named_too(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The operator runs ACTIVATION.md §8b and the worker starts admitting:
        # that transition is worth exactly one line, or nobody can tell when
        # the wallet came back.
        recorder = _Recorder()
        monkeypatch.setattr("hunter_execution_worker.risk_profile.logger", recorder)
        gate = RiskProfileGate()
        missing = _StubSession(_Row(None, None))
        await gate.resolve(cast("AsyncSession", missing), wallet=WALLET)
        linked = _StubSession(_Row(PROFILE_ID, STORED))
        await gate.resolve(cast("AsyncSession", linked), wallet=WALLET)
        await gate.resolve(cast("AsyncSession", linked), wallet=WALLET)
        assert [event for event, _ in recorder.lines] == [
            "admission_refused_no_risk_profile",
            "risk_profile_resolved",
        ]
