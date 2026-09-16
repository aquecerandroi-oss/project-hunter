"""T4.28h — check 10 with the owner's allowance: an unknown creator may pass when
the dev's share was **measured** and is within the cap.

Measured on 16/09/2026 (R5, ``obsidian/03-TRADING/Meme/Estudo-2026-09-16-admissao-real-o-que-recusa.md``):
11 of 22 real orders were refused ``creator_flow_unknown`` because
``meme_features_1m.creator_sold`` only becomes non-null +123 to +441 s after the
coin is created while the entry happens at 30–300 s. The desk's own gate
(``operator/5``, E1 arm 2, ``creator_unknown_allowed_if_dev_measured``) already
allows that coin when ``dev_share`` is measured and ≤ 10 %, so the desk proposed
what the executor refused. This table pins the two halves of the switch: **off**
(the default, and the whole of today's behaviour) and **on** (the owner's
decision), crossed with a dev share that is small, large or absent.

The allowance is never a rescue of a **known** net seller: that is the dump the
check exists to barrar, and no environment variable moves it.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from hunter_risk_meme import MemeDecision, MemePolicyMissing, limits_from_env
from hunter_risk_meme.decision import CheckState, MemeCheck

from .factories import context, decide, limits

pytestmark = pytest.mark.unit

CAP = Decimal("0.10")
POLICY = {
    "MEME_WALLET_MAX_SOL": "0.5",
    "MEME_MAX_SOL_PER_TRADE": "0.02",
    "MEME_DAILY_LOSS_CAP_SOL": "0.05",
    "MEME_MAX_OPEN_POSITIONS": "2",
    "MEME_COOLDOWN_S": "1800",
}
ENV_FLAG = "MEME_CREATOR_UNKNOWN_ALLOWED_IF_DEV_MEASURED"
ENV_CAP = "MEME_CREATOR_UNKNOWN_MAX_DEV_SHARE_PCT"


def _creator(decision: MemeDecision) -> MemeCheck:
    checks = {c.name: c for c in decision.checks}
    return checks["creator_behaviour"]


# ---- the switch is off: nothing changed -------------------------------------


@pytest.mark.parametrize("dev", [None, Decimal("0.05"), Decimal("0.11")])
def test_with_the_switch_off_an_unknown_creator_still_refuses_by_name(dev: Decimal | None) -> None:
    decision = decide(ctx=context(creator_net_sol=None, dev_share_pct=dev))
    check = _creator(decision)
    assert check.state is CheckState.UNAVAILABLE
    assert check.refusal == "creator_flow_unknown"
    assert decision.approved is False


def test_the_paper_preset_has_the_allowance_off() -> None:
    assert limits().creator_unknown_allowed_if_dev_measured is False
    assert limits().creator_unknown_max_dev_share_pct == CAP


# ---- the switch is on --------------------------------------------------------


@pytest.mark.parametrize("dev", ["0.05", "0.10", "0"])
def test_a_measured_dev_share_within_the_cap_lets_the_unknown_creator_pass(dev: str) -> None:
    decision = decide(
        lim=limits(creator_unknown_allowed_if_dev_measured=True),
        ctx=context(creator_net_sol=None, dev_share_pct=Decimal(dev)),
    )
    check = _creator(decision)
    assert check.state is CheckState.PASSED
    assert check.refusal is None
    assert check.message == "creator_unknown_dev_share_measured"
    assert (check.value, check.limit) == (Decimal(dev), CAP)
    assert decision.approved is True, decision.refusals


def test_the_admission_json_tells_unknown_but_allowed_from_known_good() -> None:
    allowed = decide(
        lim=limits(creator_unknown_allowed_if_dev_measured=True),
        ctx=context(creator_net_sol=None, dev_share_pct=Decimal("0.05")),
    ).to_jsonable()
    known_good = decide().to_jsonable()
    line = next(c for c in allowed["checks"] if c["name"] == "creator_behaviour")
    good = next(c for c in known_good["checks"] if c["name"] == "creator_behaviour")
    assert line["state"] == good["state"] == "passed"
    assert line["message"] == "creator_unknown_dev_share_measured"
    assert good["message"] != line["message"], "the desk must be able to tell them apart"


def test_a_dev_share_above_the_cap_keeps_the_same_refusal_name_and_publishes_the_cap() -> None:
    decision = decide(
        lim=limits(creator_unknown_allowed_if_dev_measured=True),
        ctx=context(creator_net_sol=None, dev_share_pct=Decimal("0.11")),
    )
    check = _creator(decision)
    assert check.state is CheckState.UNAVAILABLE
    assert check.refusal == "creator_flow_unknown", "no new refusal name for the cap case"
    assert (check.value, check.limit) == (Decimal("0.11"), CAP)
    assert "0.10" in check.message
    assert decision.approved is False


def test_an_unmeasured_dev_share_vouches_for_nothing() -> None:
    decision = decide(
        lim=limits(creator_unknown_allowed_if_dev_measured=True),
        ctx=context(creator_net_sol=None, dev_share_pct=None),
    )
    check = _creator(decision)
    assert check.state is CheckState.UNAVAILABLE
    assert check.refusal == "creator_flow_unknown"
    assert check.value is None and check.limit == CAP


def test_a_known_net_seller_is_never_rescued_by_a_small_dev_share() -> None:
    decision = decide(
        lim=limits(creator_unknown_allowed_if_dev_measured=True),
        ctx=context(creator_net_sol=Decimal("-0.5"), dev_share_pct=Decimal("0.01")),
    )
    check = _creator(decision)
    assert check.state is CheckState.FAILED
    assert check.refusal == "creator_net_seller"


def test_the_owners_cap_from_the_environment_is_what_the_check_applies() -> None:
    lim = limits_from_env({**POLICY, ENV_FLAG: "true", ENV_CAP: "0.02"})
    assert lim.creator_unknown_allowed_if_dev_measured is True
    inside = _creator(
        decide(lim=lim, ctx=context(creator_net_sol=None, dev_share_pct=Decimal("0.02")))
    )
    outside = _creator(
        decide(lim=lim, ctx=context(creator_net_sol=None, dev_share_pct=Decimal("0.03")))
    )
    assert inside.state is CheckState.PASSED and inside.limit == Decimal("0.02")
    assert outside.refusal == "creator_flow_unknown" and outside.limit == Decimal("0.02")


# ---- the environment ---------------------------------------------------------


def test_an_absent_flag_is_off_and_not_a_missing_policy() -> None:
    lim = limits_from_env(POLICY)
    assert lim.creator_unknown_allowed_if_dev_measured is False
    assert lim.creator_unknown_max_dev_share_pct == CAP


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "yes", "on"])
def test_the_flag_vocabulary_of_the_other_flags(raw: str) -> None:
    assert limits_from_env({**POLICY, ENV_FLAG: raw}).creator_unknown_allowed_if_dev_measured


@pytest.mark.parametrize("raw", ["0", "false", "no", "off", "  "])
def test_anything_the_owner_wrote_as_off_is_off(raw: str) -> None:
    assert not limits_from_env({**POLICY, ENV_FLAG: raw}).creator_unknown_allowed_if_dev_measured


@pytest.mark.parametrize("raw", ["maybe", "sim", "2", "on!"])
def test_a_flag_nobody_can_read_refuses_the_boot_by_name(raw: str) -> None:
    with pytest.raises(MemePolicyMissing) as info:
        limits_from_env({**POLICY, ENV_FLAG: raw})
    assert info.value.invalid == (ENV_FLAG,)
    assert info.value.missing == ()


@pytest.mark.parametrize("raw", ["ten percent", "1.5", "-0.1", "NaN"])
def test_a_cap_that_is_not_a_fraction_refuses_the_boot_by_name(raw: str) -> None:
    with pytest.raises(MemePolicyMissing) as info:
        limits_from_env({**POLICY, ENV_CAP: raw})
    assert info.value.invalid == (ENV_CAP,)
