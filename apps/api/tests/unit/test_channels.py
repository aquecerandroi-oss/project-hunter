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


# --- HIGH (T1.6b proof, 2026-09-05, found by Astra's second opinion) ------
# Binance USDS-M lists perpetuals with Chinese symbols; four of them were in
# the top 100 by 24h volume on 2026-09-05 (rank 19, 42, 63, 81). The worker
# monitors them and publishes rt:market:binance:<symbol>; an ASCII-only
# grammar refused the subscription, so those detail pages showed a frozen
# price while every other market updated live.
@pytest.mark.parametrize("symbol", ["牛来USDT", "龙虾USDT", "币安人生USDT", "我踏马来了USDT"])
def test_a_unicode_symbol_the_worker_publishes_is_authorized(
    member: Principal, symbol: str
) -> None:
    assert is_authorized(f"rt:market:binance:{symbol}", member) is True


# Property check, not a regression: the ASCII rows below were already refused
# before the widening, and the Unicode ones were refused for the unrelated
# reason that the old class rejected the ideographs. They exist so that the
# next change to this grammar cannot quietly let a separator or a wildcard in.
@pytest.mark.parametrize(
    "channel",
    [
        "rt:market:binance:牛来USDT\n",  # newline still refused (\Z, not $)
        "rt:market:binance:牛来:USDT",  # ':' is the segment separator
        "rt:market:binance:牛来*USDT",  # wildcards still refused
        "rt:market:binance:牛来 USDT",  # whitespace still refused
        "rt:market:binance:BTC*USDT",  # the same, in plain ASCII
        "rt:market:binance:BTC?USDT",
        "rt:market:binance:BTC[US]DT",
        "rt:market:binance:BTC USDT",
        "rt:market:binance:BTC:USDT",
    ],
)
def test_the_grammar_still_refuses_separators_and_wildcards(
    member: Principal, channel: str
) -> None:
    assert is_authorized(channel, member) is False
