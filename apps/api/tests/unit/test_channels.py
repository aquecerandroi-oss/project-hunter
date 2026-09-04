"""Channel authorization — the grammar, not the socket.

``is_authorized`` is the last thing between a subscribe frame and a Redis
subscription, so the grammar it accepts is a security boundary: a name that
slips through is a name whose messages get delivered down that socket.
"""

from __future__ import annotations

import uuid

import pytest

from hunter_api.auth.principal import Membership, Principal
from hunter_api.realtime.channels import is_authorized
from hunter_core.domain.enums import MemberStatus, OrganizationRole

pytestmark = pytest.mark.unit

ORG = uuid.UUID("0189d6b1-8b3f-7c2a-9e41-2b7c5d3f1a90")
OTHER_ORG = uuid.uuid4()


@pytest.fixture
def member() -> Principal:
    return Principal(
        user_id=uuid.uuid4(),
        external_auth_id="user_FAKE_channels",
        memberships=(
            Membership(org_id=ORG, role=OrganizationRole.TRADER, status=MemberStatus.ACTIVE),
        ),
    )


def test_a_members_own_org_channel_is_authorized(member: Principal) -> None:
    assert is_authorized(f"rt:org:{ORG}:risk", member) is True


@pytest.mark.parametrize(
    "channel",
    [
        "rt:radar\n",
        "rt:market:binance:BTCUSDT\n",
        "rt:market:binance:BTCUSDT\nrt:org:x",
    ],
)
def test_a_trailing_newline_does_not_smuggle_a_channel_past_the_grammar(
    member: Principal, channel: str
) -> None:
    """``$`` matches before a trailing newline; ``\\Z`` does not.

    With ``$``, ``rt:market:a:B\\n`` is accepted and the *name that was
    validated* is not the name that reaches Redis — the one that reaches Redis
    has a newline in it, which is a protocol separator in RESP.
    """
    assert is_authorized(channel, member) is False


def test_an_uppercase_uuid_is_refused(member: Principal) -> None:
    """``uuid.UUID`` parses both cases, so an upper-case spelling authorizes
    correctly *and* produces a different Redis channel name than the one the
    publishers use — a subscription that is authorized and then silent.
    Refusing it keeps one canonical spelling per organization.
    """
    assert is_authorized(f"rt:org:{str(ORG).upper()}:risk", member) is False


def test_another_orgs_channel_is_refused(member: Principal) -> None:
    assert is_authorized(f"rt:org:{OTHER_ORG}:risk", member) is False


def test_a_suspended_membership_authorizes_nothing() -> None:
    suspended = Principal(
        user_id=uuid.uuid4(),
        external_auth_id="user_FAKE_suspended",
        memberships=(
            Membership(org_id=ORG, role=OrganizationRole.OWNER, status=MemberStatus.SUSPENDED),
        ),
    )

    assert is_authorized(f"rt:org:{ORG}:risk", suspended) is False


@pytest.mark.parametrize(
    "channel",
    ["rt:radar", "rt:system", "rt:market:binance:BTCUSDT", "rt:market:bybit:ETH-PERP"],
)
def test_public_channels_are_authorized_for_anyone(member: Principal, channel: str) -> None:
    assert is_authorized(channel, member) is True
