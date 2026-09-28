"""Everton's audited per-mint exception (decision 2026-09-28,
``obsidian/06-DECISIONS/2026-09-28-excecao-auditada-token-golpe.md``) — pure
pieces and the reader's wiring, fakes only (no network, no DB).

What is pinned: an exception takes **only its own mint** off the "unrecognized"
list, and only while the chain still shows what was verified (same program,
same decimals, not opaque, at most the recorded atoms, frozen when the row
requires it) — anything else keeps the mint named (fail closed); the excepted
mints are reported apart (verdict, admission payload, heartbeat); and nothing
but ``wallet_exceptions.py`` in the runtime code reads the table, so an
exception can never enable a buy, a sell or any other interaction."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import ast
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from hunter_exchanges.pumpfun.solana_codec import TOKEN_2022_PROGRAM_ID, TOKEN_PROGRAM_ID
from hunter_meme_executor.chain import TokenHolding, parse_token_accounts
from hunter_meme_executor.wallet_exceptions import (
    EXCEPTIONS_TABLE,
    HoldingException,
    split_excepted,
)
from hunter_meme_executor.wallet_holdings import HoldingsVerdict, WalletHoldingsReader

pytestmark = pytest.mark.unit

SCAM = "DgY9Z8xPG1346Ydrq98ASAZcVdyrurT4tCQ7TDapHcJg"
OTHER = "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn"
OWNER = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
ATOMS = 100_000 * 10**6
T0 = datetime(2026, 9, 28, 12, tzinfo=UTC)


def _h(
    mint: str = SCAM,
    amount: int = ATOMS,
    *,
    program: str = TOKEN_2022_PROGRAM_ID,
    decimals: int = 6,
    opaque: bool = False,
    frozen: bool = True,
    state: str | None = None,
) -> TokenHolding:
    held = state if state is not None else ("frozen" if frozen else "initialized")
    return TokenHolding(mint, program, amount, decimals, opaque, held)


def _rule(
    mint: str = SCAM,
    *,
    program: str = TOKEN_2022_PROGRAM_ID,
    max_atoms: int = ATOMS,
    decimals: int = 6,
    require_frozen: bool = True,
    exception_id: str = "0199a8b0-0000-7000-8000-00000000dg19",
) -> HoldingException:
    return HoldingException(program, mint, max_atoms, decimals, require_frozen, exception_id, T0)


# ------------------------------------------------------------------ the predicate
def test_the_exception_takes_only_its_own_mint_off_the_list() -> None:
    holdings = (_h(), _h(OTHER, 5_000_000, program=TOKEN_PROGRAM_ID, frozen=False))
    unrecognized, excepted = split_excepted((SCAM, OTHER), holdings, (_rule(),))
    assert unrecognized == (OTHER,) and excepted == (SCAM,)


def test_an_exception_for_one_mint_never_covers_another() -> None:
    unrecognized, excepted = split_excepted((OTHER,), (_h(OTHER),), (_rule(SCAM),))
    assert unrecognized == (OTHER,) and excepted == ()


def test_no_exception_leaves_the_list_untouched() -> None:
    assert split_excepted((SCAM, OTHER), (_h(), _h(OTHER)), ()) == ((SCAM, OTHER), ())


@pytest.mark.parametrize(
    ("holdings", "why"),
    [
        ((_h(program=TOKEN_PROGRAM_ID),), "another program"),
        ((_h(decimals=9),), "other decimals"),
        ((_h(opaque=True),), "a confidential balance proves nothing"),
        ((_h(amount=ATOMS + 1),), "more than was verified: a buy on top"),
        ((_h(amount=ATOMS // 2), _h(amount=ATOMS // 2 + 1)), "the total is judged, not an account"),
        ((_h(frozen=False),), "thawed: the remedy (empty it) works again"),
        ((_h(amount=1), _h(amount=1, frozen=False)), "one thawed account is enough"),
        ((_h(), _h(program=TOKEN_PROGRAM_ID, frozen=True)), "one account outside the row"),
    ],
)
def test_the_mint_stays_named_unless_the_chain_shows_what_was_verified(
    holdings: tuple[TokenHolding, ...], why: str
) -> None:
    unrecognized, excepted = split_excepted((SCAM,), holdings, (_rule(),))
    assert (unrecognized, excepted) == ((SCAM,), ()), why


def test_an_unfrozen_exception_is_bounded_by_its_atoms() -> None:
    rule = _rule(require_frozen=False)
    assert split_excepted((SCAM,), (_h(frozen=False),), (rule,)) == ((), (SCAM,))
    assert split_excepted((SCAM,), (_h(amount=ATOMS + 1, frozen=False),), (rule,)) == ((SCAM,), ())


@pytest.mark.parametrize("state", ["", "uninitialized", "Frozen", "weird"])
def test_an_unknown_account_state_is_never_excepted_even_when_unfrozen_is_allowed(
    state: str,
) -> None:
    """Astra (design, must-fix 3): ``--allow-unfrozen`` waives the freeze, never
    the integrity of the read — a state the parser did not recognize is not
    "validly unfrozen"."""
    rule = _rule(require_frozen=False)
    assert split_excepted((SCAM,), (_h(state=state),), (rule,)) == ((SCAM,), ())


def test_a_named_mint_with_no_account_in_the_read_is_never_excepted() -> None:
    assert split_excepted((SCAM,), (), (_rule(),)) == ((SCAM,), ())


def test_the_output_keeps_the_sorted_order_of_the_named_list() -> None:
    third = "Zzz9Z8xPG1346Ydrq98ASAZcVdyrurT4tCQ7TDapHcJg"
    named = tuple(sorted((SCAM, OTHER, third)))
    holdings = (_h(), _h(OTHER), _h(third))
    unrecognized, excepted = split_excepted(named, holdings, (_rule(), _rule(third)))
    assert unrecognized == (OTHER,) and excepted == (SCAM, third)


# ------------------------------------------------------------------ the chain read
def test_the_parsed_account_state_is_kept_verbatim() -> None:
    def account(state: str | None) -> dict[str, Any]:
        info: dict[str, Any] = {
            "mint": SCAM,
            "owner": OWNER,
            "tokenAmount": {"amount": str(ATOMS), "decimals": 6},
        }
        if state is not None:
            info["state"] = state
        return {
            "pubkey": "CX7sPvh759HBN7Hd9hfXqWEyD5nN292YzLzv15Hxrj9i",
            "account": {"data": {"parsed": {"info": info}}, "owner": TOKEN_2022_PROGRAM_ID},
        }

    for state, kept in (("frozen", "frozen"), ("initialized", "initialized"), (None, "")):
        result = {"context": {"slot": 1}, "value": [account(state)]}
        found, _ = parse_token_accounts(result, owner=OWNER, program=TOKEN_2022_PROGRAM_ID)
        assert found[0].state == kept, state


# ------------------------------------------------------------------ reporting
def test_the_admission_records_which_exception_excepted_each_mint() -> None:
    """Database-architect review (must-fix 2): a verdict is reused for up to 30 s
    without re-reading, so the row that decided cannot be reconstructed from
    ``created_at``/``revoked_at`` — the admission records the exception's id."""
    verdict = HoldingsVerdict((OTHER,), 3, (9, 9), T0, excepted=(_rule(),))
    payload = verdict.as_json()
    assert payload["unrecognized"] == [OTHER] and payload["unrecognized_count"] == 1
    assert payload["excepted"] == [
        {
            "mint": SCAM,
            "exception_id": "0199a8b0-0000-7000-8000-00000000dg19",
            "created_at": T0.isoformat(),
        }
    ]
    assert payload["excepted_count"] == 1


def test_the_heartbeat_publishes_the_excepted_mints_apart() -> None:
    verdict = HoldingsVerdict((), 3, (9, 9), T0, excepted=(_rule(),))
    reader = WalletHoldingsReader(last=verdict)
    fields = reader.describe(T0)
    assert fields["wallet_unrecognized_count"] == "0" and fields["wallet_unrecognized_mints"] == ""
    assert fields["wallet_excepted_count"] == "1" and fields["wallet_excepted_mints"] == SCAM


def test_an_unread_wallet_publishes_empty_excepted_fields() -> None:
    fields = WalletHoldingsReader().describe(T0)
    assert fields["wallet_excepted_count"] == "" and fields["wallet_excepted_mints"] == ""


# ------------------------------------------------------------------ one reader only
_REPO = Path(__file__).resolve().parents[3]
_RUNTIME = ("apps", "packages", "services")
_ALLOWED = {
    "services/meme-executor/hunter_meme_executor/wallet_exceptions.py",
    "packages/core/hunter_core/db/models/meme_wallet_exceptions.py",
}
"""The one runtime reader, and the ORM declaration ``alembic check`` compares.
The migration (``infra/migrations``) and the operator's CLI (``infra/scripts``)
are not runtime code; tests are excluded."""


_SKIP = {"tests", "node_modules", ".next", "__pycache__", ".turbo", "dist"}


def test_no_other_runtime_code_reads_the_exceptions_table() -> None:
    pattern = re.compile(re.escape(EXCEPTIONS_TABLE))
    readers: set[str] = set()
    for root in _RUNTIME:
        for folder, dirs, files in os.walk(_REPO / root):  # never follows links
            dirs[:] = [d for d in dirs if d not in _SKIP]
            for name in files:
                path = Path(folder) / name
                if path.suffix not in {".py", ".ts", ".tsx", ".sql"}:
                    continue
                if pattern.search(path.read_text(encoding="utf-8", errors="replace")):
                    readers.add(path.relative_to(_REPO).as_posix())
    assert readers == _ALLOWED, readers


_SYMBOLS = frozenset({"split_excepted", "active_exceptions", "MemeWalletHoldingException"})
_MODULES = (
    "hunter_meme_executor.wallet_exceptions",
    "hunter_core.db.models.meme_wallet_exceptions",
)
_IMPORTERS_ALLOWED = {
    "services/meme-executor/hunter_meme_executor/wallet_holdings.py",
    "packages/core/hunter_core/db/models/__init__.py",
}
"""Guardian review (4): who may import the exception module, its two functions or
its ORM class — the holdings verdict and the models package. The operator's CLI
(``infra/scripts/wallet_holding_exception*.py``) and the migration (``infra/migrations``)
are allowed too; today neither imports them (the CLI writes by SQL)."""
_TOOLING_ALLOWED = ("infra/scripts/wallet_holding_exception", "infra/migrations/")


def _uses(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module in _MODULES or module.endswith(".wallet_exceptions"):
                return True
            if any(a.name in _SYMBOLS or a.name == "wallet_exceptions" for a in node.names):
                return True
        elif isinstance(node, ast.Import):
            if any(a.name in _MODULES for a in node.names):
                return True
        elif isinstance(node, ast.Name) and node.id in _SYMBOLS:
            return True
        elif isinstance(node, ast.Attribute) and node.attr in _SYMBOLS:
            return True
    return False


def test_only_the_verdict_and_the_models_import_the_exception_code() -> None:
    importers: set[str] = set()
    for root in (*_RUNTIME, "infra"):
        for folder, dirs, files in os.walk(_REPO / root):  # never follows links
            dirs[:] = [d for d in dirs if d not in _SKIP]
            for name in files:
                path = Path(folder) / name
                if path.suffix != ".py":
                    continue
                source = path.read_text(encoding="utf-8", errors="replace")
                if _uses(ast.parse(source)):
                    importers.add(path.relative_to(_REPO).as_posix())
    strangers = {f for f in importers - _IMPORTERS_ALLOWED if not f.startswith(_TOOLING_ALLOWED)}
    assert strangers == set(), strangers
    assert "services/meme-executor/hunter_meme_executor/wallet_holdings.py" in importers
