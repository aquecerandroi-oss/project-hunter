"""The origin of a proposal, and the key that makes a replay a replay — T3.12.

Nothing here touches a database: the origin is decided before any lock is taken,
because a request that may not become a proposal must not consume the wallet's
serialisation point (and must not take a place in the FIFO queue).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from hunter_core.admission.sources import (
    OriginRefused,
    ProposalRequest,
    admission_key,
    resolve_source,
)
from hunter_core.domain.enums import MarketType, ProposalSource, TradeDirection
from hunter_core.strategies.envelope import PURPOSE_RESEARCH_ONLY, AssumedCosts
from hunter_risk.inputs import MarketIdentity

pytestmark = pytest.mark.unit

COSTS = AssumedCosts(
    spread_bps=Decimal(2), slippage_bps=Decimal(5), fee_bps=Decimal(4), max_entry_delay_s=60
)
MARKET = MarketIdentity(
    exchange="binance",
    symbol="SOLUSDT",
    market_type=MarketType.SPOT,
    base_asset="SOL",
    quote_asset="USDT",
)


def request(**overrides: object) -> ProposalRequest:
    base: dict[str, object] = {
        "client_key": "order-1",
        "organization_id": uuid.uuid4(),
        "portfolio_id": uuid.uuid4(),
        "market_id": uuid.uuid4(),
        "market": MARKET,
        "direction": TradeDirection.LONG,
        "entry_ref": Decimal(100),
        "stop": Decimal("97.5"),
        "assumed_costs": COSTS,
        "actor_id": str(uuid.uuid4()),
    }
    base.update(overrides)
    return ProposalRequest.model_validate(base)


class TestOnlyTwoOriginsExist:
    def test_manual_and_agent_resolve_to_the_enum(self) -> None:
        assert resolve_source("manual") is ProposalSource.MANUAL
        assert resolve_source(ProposalSource.AGENT) is ProposalSource.AGENT

    def test_the_shadow_bridge_is_not_an_origin(self) -> None:
        """``proposal_source`` has two members and a label is a promise."""
        with pytest.raises(OriginRefused, match="shadow_bridge"):
            resolve_source("shadow_bridge")

    def test_research_only_never_becomes_a_proposal(self) -> None:
        with pytest.raises(OriginRefused, match=PURPOSE_RESEARCH_ONLY):
            request(purpose=PURPOSE_RESEARCH_ONLY).origin(ProposalSource.MANUAL)

    def test_an_agent_proposal_names_the_agent_that_asked(self) -> None:
        with pytest.raises(OriginRefused, match="agent_id"):
            request().origin(ProposalSource.AGENT)

    def test_a_manual_order_never_names_an_agent(self) -> None:
        with pytest.raises(OriginRefused, match="manual"):
            request(agent_id=uuid.uuid4()).origin(ProposalSource.MANUAL)

    def test_a_live_manual_order_passes(self) -> None:
        assert request().origin(ProposalSource.MANUAL) is ProposalSource.MANUAL

    def test_the_stop_geometry_of_a_long_is_refused_at_the_door(self) -> None:
        """A stop at or above the reference is not a stop; it is a caller bug."""
        with pytest.raises(ValueError, match="stop"):
            request(stop=Decimal(100))


class TestMoneyIsNeverAFloat:
    @pytest.mark.parametrize("field", ["entry_ref", "stop", "requested_notional"])
    def test_a_float_price_is_refused_at_the_door(self, field: str) -> None:
        """0,1 + 0,2 must not become 0,30000000000000004 inside a decision."""
        with pytest.raises(ValueError, match="float"):
            request(**{field: 100.5})

    def test_a_decimal_string_is_accepted(self) -> None:
        assert request(entry_ref=Decimal("100.5")).entry_ref == Decimal("100.5")


class TestTheIdempotencyKeyCarriesItsOrigin:
    def test_the_same_client_key_from_two_origins_is_two_proposals(self) -> None:
        manual = admission_key(ProposalSource.MANUAL, "abc")
        agent = admission_key(ProposalSource.AGENT, "abc")
        assert manual != agent
        assert manual == "manual:abc"

    def test_the_key_is_stable(self) -> None:
        assert admission_key(ProposalSource.MANUAL, "abc") == admission_key(
            ProposalSource.MANUAL, "abc"
        )

    def test_an_empty_client_key_is_not_a_key(self) -> None:
        with pytest.raises(ValueError, match="client_key"):
            admission_key(ProposalSource.MANUAL, "   ")
