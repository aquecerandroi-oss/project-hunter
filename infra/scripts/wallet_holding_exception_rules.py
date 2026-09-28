"""The policy half of ``wallet_holding_exception.py`` (F1, decision 2026-09-28,
``obsidian/06-DECISIONS/2026-09-28-excecao-auditada-token-golpe.md``): what the
chain must show before the owner may except a mint from §3.2's
``wallet_unrecognized_holdings``, and the evidence the row keeps. Pure: the two
RPC answers come in as arguments; no network, no database.

**The chain facts** are read through the executor's own parser
(``hunter_meme_executor.chain.parse_token_accounts``), so the row describes
exactly what check 17 will see. ``getTokenAccountsByOwner(wallet, {mint})`` and
``getAccountInfo(mint)``, ``jsonParsed``, ``confirmed``.

**The policy**, every refusal by name, nothing written:

- ``mint_recognized`` — a mint the executor accounts for (open position,
  in-flight buy, closed ≤ 60 s — ``wallet_holdings.recognized_mints``) or a quote
  mint (WSOL, the treasury's USDC) needs no exception, and excepting it would
  outlive the position;
- ``account_not_found`` / ``program_mismatch`` / ``mint_not_found`` /
  ``chain_answer_malformed`` — the chain must show the holding under the
  program given;
- ``balance_is_dust`` — check 17 does not name it; ``account_opaque`` — a
  confidential balance proves nothing and the executor never excepts it;
  ``decimals_mismatch`` — the accounts and the mint must agree;
- ``account_not_frozen_by_third_party`` — **by default** every account of the
  mint must be ``frozen`` and the mint's freeze authority must exist and not be
  the wallet. Why: the contract's remedy ("zero the balance", §3.2) works for
  any token that is not frozen by someone else — an exception there would only
  hide a removable holding (a manual buy, an airdrop one could burn) instead of
  removing it, which is the argument the owner accepted against auto-ignoring
  (option 2). ``--allow-unfrozen`` waives this, explicitly, and is recorded in
  the evidence; the row then requires the freeze only if one was observed (a
  third-party freeze seen now is always required later) and still caps atoms;
- ``account_state_unknown`` — under ``--allow-unfrozen`` the state must still be
  one the parser recognizes (Astra, design review): unknown is never "unfrozen".

The cap is the **observed total**, no margin (Astra): a buy on top is named again.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, cast

from hunter_meme_executor.chain import TokenHolding, parse_token_accounts
from hunter_meme_executor.wallet_holdings import QUOTE_MINTS, unrecognized_mints

__all__ = [
    "HOW",
    "ChainFacts",
    "Plan",
    "Refused",
    "judge",
    "read_facts",
    "require_pubkey",
    "require_reason",
]

HOW: Final = (
    "getTokenAccountsByOwner(wallet, {mint}) + getAccountInfo(mint), jsonParsed, confirmed; "
    "accounts parsed by hunter_meme_executor.chain.parse_token_accounts"
)
_PUBKEY = re.compile(r"[1-9A-HJ-NP-Za-km-z]{32,44}")
_KNOWN_STATES: Final = frozenset({"initialized", "frozen"})


class Refused(Exception):
    """A named refusal; ``str(exc)`` starts with the reason."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ChainFacts:
    program: str
    mint: str
    holdings: tuple[TokenHolding, ...]
    accounts: tuple[dict[str, Any], ...]
    """Per account: address, state, amount, decimals, delegate, extension names."""
    mint_decimals: int
    freeze_authority: str | None
    mint_authority: str | None
    slots: dict[str, int]
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class Plan:
    max_atoms: int
    decimals: int
    require_frozen: bool
    evidence: dict[str, Any]


def require_pubkey(value: str, what: str) -> str:
    if not _PUBKEY.fullmatch(value or ""):
        raise Refused("invalid_pubkey", f"{what} {value!r} is not a base58 public key")
    return value


def require_reason(reason: str | None) -> str:
    if reason is None or len(reason.strip()) < 10:
        raise Refused("reason_required", "--reason needs at least 10 characters")
    return reason.strip()


def _account_evidence(entry: dict[str, Any]) -> dict[str, Any]:
    info = cast(dict[str, Any], entry["account"]["data"]["parsed"]["info"])
    extensions = cast(list[dict[str, Any]], info.get("extensions") or [])
    return {
        "address": str(entry["pubkey"]),
        "state": info.get("state") if isinstance(info.get("state"), str) else None,
        "amount": str(info["tokenAmount"]["amount"]),
        "decimals": info["tokenAmount"]["decimals"],
        "delegate": info.get("delegate"),
        "extensions": [str(e.get("extension", "")) for e in extensions],
    }


def read_facts(
    accounts_result: Any,
    mint_result: Any,
    *,
    wallet: str,
    program: str,
    mint: str,
    observed_at: datetime,
) -> ChainFacts:
    """The two RPC answers → facts, or a named refusal."""
    try:
        value: Any = accounts_result["value"]
        accounts_result["context"]["slot"]  # a missing slot is a malformed answer
        mint_value = mint_result["value"]
        if not isinstance(value, list):
            raise TypeError("accounts value is not a list")
        entries = cast(list[dict[str, Any]], value)
        owners = {str(e["account"]["owner"]) for e in entries}
    except (KeyError, TypeError) as exc:
        raise Refused("chain_answer_malformed", "unexpected RPC shape") from exc
    if not entries:
        raise Refused("account_not_found", f"wallet holds no account of {mint}")
    if owners != {program}:
        raise Refused("program_mismatch", f"accounts owned by {sorted(owners)}, not {program}")
    try:
        holdings, slot = parse_token_accounts(accounts_result, owner=wallet, program=program)
    except ValueError as exc:
        raise Refused("chain_answer_malformed", "token accounts") from exc
    if mint_value is None:
        raise Refused("mint_not_found", mint)
    try:
        if mint_value["owner"] != program:
            raise Refused("program_mismatch", f"mint owned by {mint_value['owner']}")
        info = cast(dict[str, Any], mint_value["data"]["parsed"]["info"])
        decimals, freeze, authority = (
            info["decimals"],
            info.get("freezeAuthority"),
            info.get("mintAuthority"),
        )
        mint_slot: Any = mint_result["context"]["slot"]
    except (KeyError, TypeError, ValueError) as exc:
        raise Refused("chain_answer_malformed", "mint account") from exc
    if type(mint_slot) is not int or mint_slot < 0 or type(decimals) is not int:
        raise Refused("chain_answer_malformed", "mint slot or decimals")  # never coerced
    if any(h.mint != mint for h in holdings):
        raise Refused("chain_answer_malformed", "an account of another mint")
    return ChainFacts(
        program=program,
        mint=mint,
        holdings=holdings,
        accounts=tuple(_account_evidence(e) for e in entries),
        mint_decimals=decimals,
        freeze_authority=freeze if isinstance(freeze, str) else None,
        mint_authority=authority if isinstance(authority, str) else None,
        slots={"accounts": slot, "mint": mint_slot},
        observed_at=observed_at,
    )


def judge(
    facts: ChainFacts, *, wallet: str, recognized: frozenset[str], allow_unfrozen: bool
) -> Plan:
    """The facts → what the row records, or a named refusal (module docstring)."""
    if facts.mint in recognized | QUOTE_MINTS:
        raise Refused("mint_recognized", f"{facts.mint} is accounted for by the executor")
    if any(h.opaque for h in facts.holdings):
        raise Refused("account_opaque", "a confidential balance is never excepted")
    if {h.decimals for h in facts.holdings} != {facts.mint_decimals}:
        raise Refused("decimals_mismatch", f"mint says {facts.mint_decimals}")
    if not unrecognized_mints(facts.holdings, frozenset()):
        raise Refused("balance_is_dust", "check 17 does not name this mint")
    states = {h.state for h in facts.holdings}
    third_party = facts.freeze_authority is not None and facts.freeze_authority != wallet
    frozen_by_third_party = states == {"frozen"} and third_party
    if not allow_unfrozen and not frozen_by_third_party:
        raise Refused(
            "account_not_frozen_by_third_party",
            f"states {sorted(states)}, freeze authority {facts.freeze_authority} "
            "(empty the balance instead, or pass --allow-unfrozen explicitly)",
        )
    if not states <= _KNOWN_STATES:
        raise Refused("account_state_unknown", f"states {sorted(states)}")
    total = sum(h.amount for h in facts.holdings)
    evidence: dict[str, Any] = {
        "how": HOW,
        "observed_at": facts.observed_at.isoformat(),
        "slots": facts.slots,
        "wallet": wallet,
        "token_program": facts.program,
        "mint": facts.mint,
        "accounts": list(facts.accounts),
        "total_atoms": str(total),
        "decimals": facts.mint_decimals,
        "mint_authority": facts.mint_authority,
        "freeze_authority": facts.freeze_authority,
        "frozen_by_third_party": frozen_by_third_party,
        "allow_unfrozen": allow_unfrozen,
    }
    # Guardian (3): a freeze observed now is always required later, flag or not.
    require_frozen = frozen_by_third_party or not allow_unfrozen
    return Plan(total, facts.mint_decimals, require_frozen, evidence)
