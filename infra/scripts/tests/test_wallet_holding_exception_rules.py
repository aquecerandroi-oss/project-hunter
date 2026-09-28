"""``wallet_holding_exception_rules`` — the audited exception's chain facts and
policy, pure (no network, no DB). Decision 2026-09-28
(``obsidian/06-DECISIONS/2026-09-28-excecao-auditada-token-golpe.md``).

What is pinned: the chain answers are read through the executor's own parser
(so the row describes exactly what check 17 will see); every refusal is named
(account not found, another program, mint unknown, malformed answer, dust,
opaque, decimals disagree, recognized or quote mint, not frozen by a third
party, unknown state); the default demands a freeze by a third-party authority
and ``--allow-unfrozen`` is explicit and recorded; the cap is the observed
total, no margin; the evidence carries accounts, states, authorities, slots and
how it was read.
"""

from __future__ import annotations

import dataclasses
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import wallet_holding_exception_rules as rules  # noqa: E402

from hunter_exchanges.jupiter import WRAPPED_SOL_MINT  # noqa: E402
from hunter_exchanges.pumpfun.solana_codec import (  # noqa: E402
    TOKEN_2022_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
)

WALLET = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
MINT = "DgY9Z8xPG1346Ydrq98ASAZcVdyrurT4tCQ7TDapHcJg"
ACCOUNT = "CX7sPvh759HBN7Hd9hfXqWEyD5nN292YzLzv15Hxrj9i"
ISSUER = "Fr33zeAuthor1ty111111111111111111111111111111"
ATOMS = 100_000 * 10**6
T = datetime(2026, 9, 28, 12, tzinfo=UTC)


def token_account(
    *,
    address: str = ACCOUNT,
    amount: int = ATOMS,
    decimals: int = 6,
    state: str | None = "frozen",
    program: str = TOKEN_2022_PROGRAM_ID,
    extensions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    info: dict[str, Any] = {
        "isNative": False,
        "mint": MINT,
        "owner": WALLET,
        "tokenAmount": {"amount": str(amount), "decimals": decimals},
        "extensions": extensions if extensions is not None else [{"extension": "immutableOwner"}],
    }
    if state is not None:
        info["state"] = state
    return {
        "pubkey": address,
        "account": {
            "data": {"program": "spl-token-2022", "parsed": {"info": info, "type": "account"}},
            "owner": program,
        },
    }


def accounts_answer(*accounts: dict[str, Any], slot: int = 400) -> dict[str, Any]:
    return {"context": {"slot": slot}, "value": list(accounts)}


def mint_answer(
    *,
    freeze: str | None = ISSUER,
    decimals: int = 6,
    program: str = TOKEN_2022_PROGRAM_ID,
    slot: int = 401,
) -> dict[str, Any]:
    info = {"decimals": decimals, "freezeAuthority": freeze, "mintAuthority": ISSUER}
    return {
        "context": {"slot": slot},
        "value": {"data": {"parsed": {"info": info, "type": "mint"}}, "owner": program},
    }


def facts(accounts: dict[str, Any] | None = None, mint: dict[str, Any] | None = None) -> Any:
    return rules.read_facts(
        accounts_answer(token_account()) if accounts is None else accounts,
        mint_answer() if mint is None else mint,
        wallet=WALLET,
        program=TOKEN_2022_PROGRAM_ID,
        mint=MINT,
        observed_at=T,
    )


def judge(read: Any = None, **kw: Any) -> Any:
    return rules.judge(
        facts() if read is None else read,
        wallet=WALLET,
        recognized=kw.pop("recognized", frozenset()),
        allow_unfrozen=kw.pop("allow_unfrozen", False),
    )


def refused(reason: str) -> Any:
    return pytest.raises(rules.Refused, match=f"^{reason}")


# ------------------------------------------------------------------ the 28/09 fact
def test_the_frozen_scam_token_is_excepted_at_its_observed_total() -> None:
    plan = judge()
    assert (plan.max_atoms, plan.decimals, plan.require_frozen) == (ATOMS, 6, True)
    ev = plan.evidence
    assert ev["accounts"] == [
        {
            "address": ACCOUNT,
            "state": "frozen",
            "amount": str(ATOMS),
            "decimals": 6,
            "delegate": None,
            "extensions": ["immutableOwner"],
        }
    ]
    assert ev["freeze_authority"] == ISSUER and ev["frozen_by_third_party"] is True
    assert ev["total_atoms"] == str(ATOMS) and ev["allow_unfrozen"] is False
    assert ev["slots"] == {"accounts": 400, "mint": 401}
    assert ev["observed_at"] == T.isoformat() and "getTokenAccountsByOwner" in ev["how"]


# ------------------------------------------------------------------ chain refusals
def test_no_account_of_the_mint_refuses_by_name() -> None:
    with refused("account_not_found"):
        facts(accounts_answer())


def test_an_account_under_another_program_refuses_by_name() -> None:
    with refused("program_mismatch"):
        facts(accounts_answer(token_account(program=TOKEN_PROGRAM_ID)))
    with refused("program_mismatch"):
        facts(mint=mint_answer(program=TOKEN_PROGRAM_ID))


def test_an_unknown_mint_refuses_by_name() -> None:
    with refused("mint_not_found"):
        facts(mint={"context": {"slot": 1}, "value": None})


@pytest.mark.parametrize(
    "broken",
    [
        {"value": []},
        {"context": {"slot": 1}, "value": {}},
        accounts_answer(token_account(amount=-1)),
    ],
)
def test_a_malformed_accounts_answer_refuses_by_name(broken: Any) -> None:
    with refused("chain_answer_malformed"):
        facts(broken)


def test_a_malformed_mint_answer_refuses_by_name() -> None:
    with refused("chain_answer_malformed"):
        facts(mint={"context": {"slot": 1}, "value": {"data": {}, "owner": TOKEN_2022_PROGRAM_ID}})


@pytest.mark.parametrize("slot", ["401", -1, True, 4.0])
def test_the_mint_slot_is_never_coerced(slot: Any) -> None:
    """Astra (diff review): the same discipline as the accounts' slot."""
    answer = mint_answer()
    answer["context"]["slot"] = slot
    with refused("chain_answer_malformed"):
        facts(mint=answer)


# ------------------------------------------------------------------ policy
@pytest.mark.parametrize("mint", [MINT, WRAPPED_SOL_MINT])
def test_a_recognized_or_quote_mint_refuses_by_name(mint: str) -> None:
    read = facts() if mint == MINT else dataclasses.replace(facts(), mint=mint)
    with refused("mint_recognized"):
        judge(read, recognized=frozenset({MINT}) if mint == MINT else frozenset())


def test_dust_needs_no_exception() -> None:
    with refused("balance_is_dust"):
        judge(facts(accounts_answer(token_account(amount=1))))


def test_an_opaque_balance_is_never_excepted() -> None:
    ext = [{"extension": "confidentialTransferAccount"}]
    with refused("account_opaque"):
        judge(facts(accounts_answer(token_account(extensions=ext))))


def test_decimals_that_disagree_with_the_mint_refuse() -> None:
    with refused("decimals_mismatch"):
        judge(facts(mint=mint_answer(decimals=9)))


@pytest.mark.parametrize(
    ("accounts", "mint"),
    [
        (accounts_answer(token_account(state="initialized")), mint_answer()),
        (accounts_answer(token_account()), mint_answer(freeze=None)),
        (accounts_answer(token_account()), mint_answer(freeze=WALLET)),  # we could thaw it
        (
            accounts_answer(
                token_account(amount=ATOMS // 2),
                token_account(address="Other" + "1" * 39, amount=ATOMS // 2, state="initialized"),
            ),
            mint_answer(),
        ),
    ],
)
def test_by_default_only_a_third_party_freeze_is_excepted(
    accounts: dict[str, Any], mint: dict[str, Any]
) -> None:
    with refused("account_not_frozen_by_third_party"):
        judge(facts(accounts, mint))


def test_allow_unfrozen_never_loosens_an_account_observed_frozen_by_a_third_party() -> None:
    """Guardian review (3): on DgY9 itself, ``--allow-unfrozen`` must not let a
    later thaw keep the exception alive — the row still requires the freeze."""
    plan = judge(allow_unfrozen=True)
    assert plan.require_frozen is True
    assert plan.evidence["allow_unfrozen"] is True
    assert plan.evidence["frozen_by_third_party"] is True


def test_allow_unfrozen_is_explicit_recorded_and_still_capped() -> None:
    read = facts(accounts_answer(token_account(state="initialized")))
    plan = judge(read, allow_unfrozen=True)
    assert plan.require_frozen is False and plan.max_atoms == ATOMS
    assert plan.evidence["allow_unfrozen"] is True
    assert plan.evidence["frozen_by_third_party"] is False


@pytest.mark.parametrize("state", [None, "uninitialized", "weird"])
def test_an_unknown_state_refuses_even_with_allow_unfrozen(state: str | None) -> None:
    with refused("account_state_unknown"):
        judge(facts(accounts_answer(token_account(state=state))), allow_unfrozen=True)


@pytest.mark.parametrize("bad", ["", "abc", "0OIl" * 10, MINT + "x"])
def test_pubkeys_are_base58_of_the_right_length(bad: str) -> None:
    with refused("invalid_pubkey"):
        rules.require_pubkey(bad, "mint")
    assert rules.require_pubkey(MINT, "mint") == MINT


@pytest.mark.parametrize("bad", [None, "", "curto"])
def test_a_reason_of_ten_characters_is_required(bad: str | None) -> None:
    with refused("reason_required"):
        rules.require_reason(bad)
