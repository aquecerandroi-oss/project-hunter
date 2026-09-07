"""The API adapter files a **request** — T3.5, addendum condition 2. No database.

What is proved: the API never decides. It mints the manual origin, carries the
``Idempotency-Key`` through as the request's client key, computes the canonical
``request_digest`` that identifies *what was asked*, and writes one pending row —
``status = pending``, no decision, no sequence, no reservation, which is exactly
the shape ``trade_proposals_the_app_only_files_requests`` enforces in the
database (DATABASE.md §19.4). Filing the same order twice returns the row that
exists; filing a **different** order under the same key is a 409.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from hunter_api.auth.principal import Principal
from hunter_api.auth.rbac import OrgContext
from hunter_api.services import admission as adapter
from hunter_core.domain.enums import (
    MarketType,
    OrganizationRole,
    ProposalSource,
    ProposalStatus,
    TradeDirection,
)
from hunter_core.strategies.envelope import AssumedCosts
from hunter_risk.inputs import MarketIdentity

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
MARKET = MarketIdentity(
    exchange="binance",
    symbol="SOLUSDT",
    market_type=MarketType.SPOT,
    base_asset="SOL",
    quote_asset="USDT",
)
COSTS = AssumedCosts(
    spread_bps=Decimal(2), slippage_bps=Decimal(5), fee_bps=Decimal(4), max_entry_delay_s=60
)


def context() -> OrgContext:
    principal = Principal(
        user_id=uuid.uuid4(), external_auth_id="user_test", email="operator@example.com"
    )
    return OrgContext(org_id=uuid.uuid4(), role=OrganizationRole.OWNER, principal=principal)


class RecordingSession:
    """A session that only remembers the statement it was handed."""

    def __init__(self) -> None:
        self.statements: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> Any:
        self.statements.append((str(statement), params or {}))
        return None


@dataclass(frozen=True)
class _Stored:
    proposal_id: uuid.UUID
    portfolio_id: uuid.UUID
    market_id: uuid.UUID
    request_digest: str | None
    status: ProposalStatus = ProposalStatus.PENDING


async def file_order(
    monkeypatch: pytest.MonkeyPatch,
    *,
    decided: Any = None,
    pending: Any = None,
    session: Any = None,
    **overrides: Any,
) -> Any:
    async def _decided(*_: Any, **__: Any) -> Any:
        return decided

    async def _pending(*_: Any, **__: Any) -> Any:
        return pending

    monkeypatch.setattr(adapter, "find_admitted", _decided)
    monkeypatch.setattr(adapter, "find_pending", _pending)
    fields: dict[str, Any] = {
        "context": context(),
        "idempotency_key": "operator-key-1",
        "portfolio_id": uuid.uuid4(),
        "market_id": uuid.uuid4(),
        "market": MARKET,
        "direction": TradeDirection.LONG,
        "entry_ref": Decimal(100),
        "stop": Decimal("97.5"),
        "assumed_costs": COSTS,
        "now": NOW,
    }
    fields.update(overrides)
    return await adapter.file_manual_order(session or RecordingSession(), **fields)


class TestTheApiFilesARequestAndNothingElse:
    async def test_one_pending_row_with_no_decision_no_sequence_and_no_reservation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session = RecordingSession()

        filed = await file_order(monkeypatch, session=session)

        assert filed.status is ProposalStatus.PENDING
        assert filed.decided is False
        assert filed.idempotency_key == "manual:operator-key-1"
        assert filed.request_digest
        sql, params = session.statements[0]
        assert "INSERT INTO trade_proposals" in sql
        assert "'pending'" in sql
        for forbidden in ("risk_decision", "admission_seq", "reserved_", "decided_at"):
            assert forbidden not in sql
        assert params["digest"] == filed.request_digest

    async def test_the_digest_is_the_identity_of_what_was_asked_not_of_who_asked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        portfolio_id, market_id = uuid.uuid4(), uuid.uuid4()
        fixed = {"portfolio_id": portfolio_id, "market_id": market_id}

        first = await file_order(monkeypatch, **fixed)
        # A different operator, byte for byte the same order.
        other_operator = await file_order(monkeypatch, context=context(), **fixed)
        other_stop = await file_order(monkeypatch, stop=Decimal("96"), **fixed)

        assert other_operator.request_digest == first.request_digest
        assert other_stop.request_digest != first.request_digest

    async def test_a_key_that_already_named_another_order_is_a_conflict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stored = _Stored(
            proposal_id=uuid.uuid4(),
            portfolio_id=uuid.uuid4(),
            market_id=uuid.uuid4(),
            request_digest="a-digest-of-another-order",
        )

        with pytest.raises(adapter.OrderReplayConflictError) as refusal:
            await file_order(monkeypatch, pending=stored)

        assert refusal.value.status_code == 409

    async def test_refiling_the_same_order_returns_the_row_that_exists(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session = RecordingSession()
        first = await file_order(monkeypatch, session=session)
        stored = _Stored(
            proposal_id=first.proposal_id,
            portfolio_id=first.portfolio_id,
            market_id=first.market_id,
            request_digest=first.request_digest,
        )

        again = await file_order(
            monkeypatch,
            pending=stored,
            session=session,
            portfolio_id=first.portfolio_id,
            market_id=first.market_id,
        )

        assert again.proposal_id == first.proposal_id
        assert again.decided is False
        assert len(session.statements) == 1  # nothing was written the second time

    async def test_a_stop_at_or_above_the_entry_is_a_422_not_a_pending_row(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session = RecordingSession()

        with pytest.raises(adapter.OrderRefusedError) as refusal:
            await file_order(monkeypatch, session=session, stop=Decimal(101))

        assert refusal.value.status_code == 422
        assert session.statements == []

    async def test_a_float_price_never_reaches_the_database(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with pytest.raises(adapter.OrderRefusedError):
            await file_order(monkeypatch, entry_ref=100.4)  # type: ignore[arg-type]


class TestTheOriginIsAlwaysManual:
    async def test_the_idempotency_key_carries_the_origin(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        filed = await file_order(monkeypatch, idempotency_key="k")

        assert filed.idempotency_key.startswith(f"{ProposalSource.MANUAL.value}:")
