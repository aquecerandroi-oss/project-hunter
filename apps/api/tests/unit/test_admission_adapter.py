"""The API adapter files a **request** — T3.5, addendum condition 2. No database.

What is proved: the API never decides. It mints the manual origin, carries the
``Idempotency-Key`` through as the request's client key, archives the
**geometry** of the order in ``request_payload`` and writes one pending row —
``status = pending``, no decision, no sequence, no reservation, which is exactly
the shape ``trade_proposals_the_app_only_files_requests`` enforces in the
database (DATABASE.md §19.4, extended by ``0009_paper_geometry`` §21.2).

Two things changed with ``0009`` and both are asserted here: the row now carries
the eight keys the engine needs to decide it (``notes-T3.5.md`` §5.1 — before
this the worker could only log ``pending_request_without_geometry``), and it no
longer carries ``request_digest``. A proof written by the caller binds nobody
(S1 of ``review-T3.1c-security.md``): the API still *computes* the digest and
returns it as the identity of what was asked, and the engine recomputes it from
the payload when it decides. Filing the same order twice returns the row that
exists — compared on the archived payload; filing a **different** order under
the same key is a 409.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hunter_api.auth.principal import Principal
from hunter_api.auth.rbac import OrgContext
from hunter_api.services import admission as adapter
from hunter_core.admission.sources import REQUEST_PAYLOAD_KEYS
from hunter_core.domain.enums import (
    MarketType,
    OrganizationRole,
    ProposalSource,
    ProposalStatus,
    TradeDirection,
)
from hunter_core.strategies.envelope import PURPOSE_PAPER, AssumedCosts
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
    request_payload: dict[str, Any] | None = None
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
    # The double is a session only in the one method this adapter calls, which is
    # the point of it. The cast is what keeps ``pyright apps/api`` clean without
    # widening the production signature to accept anything (it was already an
    # error at HEAD, before this task touched the file).
    recorder = cast("AsyncSession", session or RecordingSession())
    return await adapter.file_manual_order(recorder, **fields)


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
        sql, _params = session.statements[0]
        assert "INSERT INTO trade_proposals" in sql
        assert "'pending'" in sql
        for forbidden in (
            "risk_decision",
            "admission_seq",
            "reserved_",
            "decided_at",
            # ``0009``: the proof and the context are the engine's, and the
            # guard refuses an INSERT by the app role that carries either.
            "request_digest",
            "kill_switch_snapshot",
        ):
            assert forbidden not in sql

    async def test_the_row_carries_the_geometry_the_engine_needs_to_decide_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """§21.1: the eight keys, all present, money as JSON strings.

        Before ``0009_paper_geometry`` a filed request could be identified and
        never decided — ``notes-T3.5.md`` §5.1 measured the execution worker
        logging ``pending_request_without_geometry`` once per second, for ever.
        The shape asserted here is the one
        ``ck_trade_proposals_request_payload_is_a_geometry`` accepts.
        """
        session = RecordingSession()
        market_id = uuid.uuid4()

        await file_order(monkeypatch, session=session, market_id=market_id)

        sql, params = session.statements[0]
        assert "request_payload" in sql
        payload = json.loads(params["payload"])
        assert set(payload) == set(REQUEST_PAYLOAD_KEYS)
        assert payload["client_key"] == "operator-key-1"
        assert payload["market_id"] == str(market_id)
        assert payload["direction"] == TradeDirection.LONG.value
        # Money is a JSON *string*: a JSON number returns as a float through most
        # parsers, and 0.30000000000000004 is what Decimal exists to prevent.
        assert payload["entry_ref"] == "100"
        assert payload["stop"] == "97.5"
        assert isinstance(payload["assumed_costs"], dict)
        # Present and null, never absent: "no target" and "the writer forgot"
        # must not look the same to a reader.
        assert payload["target"] is None
        assert payload["requested_notional"] is None

    async def test_a_ceiling_the_caller_asked_for_reaches_the_payload_as_a_string(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session = RecordingSession()

        await file_order(monkeypatch, session=session, requested_notional=Decimal("1500.25"))

        payload = json.loads(session.statements[0][1]["payload"])
        assert payload["requested_notional"] == "1500.25"

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
        """A pending row is compared on its **payload**, not on a digest.

        Since ``0009`` the API may not write ``request_digest``, so the filed row
        has none; comparing against a null would have made every reused key a
        silent replay of the first order (§21.2).
        """
        stored = _Stored(
            proposal_id=uuid.uuid4(),
            portfolio_id=uuid.uuid4(),
            market_id=uuid.uuid4(),
            request_digest=None,
            request_payload={"client_key": "operator-key-1", "stop": "1"},
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
            request_digest=None,
            request_payload=json.loads(session.statements[0][1]["payload"]),
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


class TestTheManualOrderIsBornPaper:
    async def test_the_request_is_built_with_purpose_paper(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """D10: the manual order used to default to ``live``; it migrates to
        ``paper`` in the same diff that adds the label (``sources.py:212``).

        Not observable through the row written or through ``FiledRequest`` —
        ``purpose`` decides admissibility (``ProposalRequest.origin``) and is
        never persisted in ``request_payload`` or hashed into the digest — so
        this spies on the constructor call itself.
        """
        captured: dict[str, object] = {}
        original = adapter.ProposalRequest

        class _Spy(original):  # type: ignore[misc,valid-type]
            def __init__(self, **kwargs: object) -> None:
                captured.update(kwargs)
                super().__init__(**kwargs)

        monkeypatch.setattr(adapter, "ProposalRequest", _Spy)

        await file_order(monkeypatch, session=RecordingSession())

        assert captured["purpose"] == PURPOSE_PAPER
