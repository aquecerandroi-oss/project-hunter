"""The API adapter of the admission service — T3.12, no database.

What is proved: the adapter is a *translation*, not a second decision path. It
mints the manual origin, stamps the authenticated principal as the audit actor,
carries the ``Idempotency-Key`` through as the request's client key, and turns
each domain refusal into the RFC 9457 problem that is true of it — a request
that may never be a proposal is a 422, a reused key is a 409.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest

from hunter_api.auth.principal import Principal
from hunter_api.auth.rbac import OrgContext
from hunter_api.services import admission as adapter
from hunter_core.admission.dedupe import IdempotencyConflict
from hunter_core.admission.inputs import MarketMismatch
from hunter_core.admission.sources import OriginRefused
from hunter_core.domain.enums import MarketType, OrganizationRole, TradeDirection
from hunter_core.strategies.envelope import AssumedCosts
from hunter_risk.inputs import MarketIdentity

pytestmark = pytest.mark.unit

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


async def call(monkeypatch: pytest.MonkeyPatch, spy: Any, **overrides: Any) -> Any:
    monkeypatch.setattr(adapter, "admit", spy)
    ctx = overrides.pop("context", None) or context()
    inputs = adapter.AdmissionInputs(
        liquidity=None,  # type: ignore[arg-type]
        spec=None,  # type: ignore[arg-type]
        beta=None,  # type: ignore[arg-type]
        prices={},
        betas={},
        exit_cost_rate=Decimal(0),
    )
    from datetime import UTC, datetime

    return await adapter.admit_manual_order(
        None,  # type: ignore[arg-type]
        context=ctx,
        idempotency_key=overrides.pop("idempotency_key", "operator-1"),
        portfolio_id=uuid.uuid4(),
        market_id=uuid.uuid4(),
        market=MARKET,
        direction=TradeDirection.LONG,
        entry_ref=overrides.pop("entry_ref", Decimal(100)),
        stop=overrides.pop("stop", Decimal("97.5")),
        assumed_costs=COSTS,
        inputs=inputs,
        now=datetime(2026, 9, 6, 18, 30, tzinfo=UTC),
        **overrides,
    )


class TestTheAdapterOnlyTranslates:
    async def test_the_request_carries_the_manual_origin_and_the_principal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: dict[str, Any] = {}

        async def spy(session: Any, request: Any, **kwargs: Any) -> str:
            seen["request"] = request
            seen["kwargs"] = kwargs
            return "decided"

        ctx = context()
        result = await call(monkeypatch, spy, context=ctx)

        assert result == "decided"
        assert seen["kwargs"]["source"].value == "manual"
        assert seen["request"].client_key == "operator-1"
        assert seen["request"].organization_id == ctx.org_id
        assert seen["request"].actor_id == str(ctx.principal.user_id)
        assert seen["request"].actor_type == "user"
        assert seen["request"].agent_id is None

    async def test_a_malformed_geometry_is_a_422_not_a_500(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def spy(session: Any, request: Any, **kwargs: Any) -> str:  # pragma: no cover
            raise AssertionError("the service must not be reached")

        with pytest.raises(adapter.OrderRefusedError) as caught:
            await call(monkeypatch, spy, stop=Decimal(120))
        assert caught.value.status_code == 422
        assert caught.value.type.endswith("/order-refused")

    async def test_a_reused_key_is_a_409(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def spy(session: Any, request: Any, **kwargs: Any) -> str:
            raise IdempotencyConflict("already answered proposal 1")

        with pytest.raises(adapter.OrderReplayConflictError) as caught:
            await call(monkeypatch, spy)
        assert caught.value.status_code == 409
        assert caught.value.type.endswith("/idempotency-key-conflict")

    @pytest.mark.parametrize(
        "error", [OriginRefused("research_only"), MarketMismatch("another market")]
    )
    async def test_a_request_that_may_never_be_a_proposal_is_a_422(
        self, monkeypatch: pytest.MonkeyPatch, error: Exception
    ) -> None:
        async def spy(session: Any, request: Any, **kwargs: Any) -> str:
            raise error

        with pytest.raises(adapter.OrderRefusedError) as caught:
            await call(monkeypatch, spy)
        assert caught.value.status_code == 422

    async def test_an_unopened_wallet_is_a_409(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from hunter_core.portfolio.state import WalletNotOpen

        async def spy(session: Any, request: Any, **kwargs: Any) -> str:
            raise WalletNotOpen("never opened")

        with pytest.raises(adapter.WalletNotOpenError) as caught:
            await call(monkeypatch, spy)
        assert caught.value.status_code == 409
