"""``close_empty_token_accounts_rules`` — the policy this tool adds on top of
the T4.77 close pipeline (``meme_close_atas_*``): quote mints kept, mints the
executor recognizes kept, the TOCTOU re-check of a batch, the batch size vs.
the transaction size, the ``audit_logs`` row, the in-flight SQL and the
Obsidian note gate. Labelled fixtures only (``raw_account``); no network, no
database, no key.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
for extra in (SCRIPTS_DIR, SCRIPTS_DIR / "tests"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import close_empty_token_accounts_rules as rules  # noqa: E402
from meme_close_atas_plan import build_batch_message, build_plan, parse_token_accounts  # noqa: E402
from meme_close_atas_verify import verify_close_atas_message  # noqa: E402
from obsidian_note_gate import NoteProof  # noqa: E402
from test_meme_close_atas_plan import RENT, WALLET, WSOL, raw_account  # noqa: E402

from hunter_exchanges.pumpfun.solana_codec import (  # noqa: E402
    TOKEN_2022_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
    serialize_message,
    serialize_transaction,
)
from hunter_meme_executor import wallet_holdings  # noqa: E402

PHISHING_MINT = "DgY9Z8xPG1346Ydrq98ASAZcVdyrurT4tCQ7TDapHcJg"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
RENT_2022 = 1_513_840
BLOCKHASH = "11111111111111111111111111111111"


def rows(*raw: dict[str, Any]) -> tuple[Any, ...]:
    out: list[Any] = []
    for program in (TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID):
        out.extend(
            parse_token_accounts(
                [r for r in raw if r["account"]["owner"] == program], program=program
            )
        )
    return tuple(out)


def verdicts(plan: Any) -> dict[str, str]:
    return {row.mint: verdict for row, verdict in plan.rows}


def phishing_raw(**overrides: Any) -> dict[str, Any]:
    """The 28/09 fact: Token-2022, balance 100 000 atoms, frozen by its issuer."""
    base: dict[str, Any] = {
        "program": TOKEN_2022_PROGRAM_ID,
        "mint": PHISHING_MINT,
        "amount": 100_000,
        "state": "frozen",
        "lamports": RENT_2022,
    }
    base.update(overrides)
    return raw_account(99, **base)


# --- verdicts


def test_empty_classic_and_token_2022_accounts_are_candidates() -> None:
    plan = rules.judge(
        rows(raw_account(1), raw_account(2, program=TOKEN_2022_PROGRAM_ID, lamports=RENT_2022)),
        wallet=WALLET,
        recognized=frozenset(),
    )
    assert [v for _, v in plan.rows] == ["close", "close"]
    assert plan.total_recoverable == RENT + RENT_2022


@pytest.mark.parametrize("amount", [100_000, 0])
def test_the_frozen_phishing_account_is_skipped_by_name_and_never_selected(amount: int) -> None:
    plan = rules.judge(rows(phishing_raw(amount=amount)), wallet=WALLET, recognized=frozenset())
    assert verdicts(plan)[PHISHING_MINT] == "skipped:never_touch:phishing"
    assert plan.selected == ()


def test_any_other_frozen_account_is_skipped_as_frozen() -> None:
    frozen = raw_account(5, state="frozen")
    plan = rules.judge(rows(frozen), wallet=WALLET, recognized=frozenset())
    assert [v for _, v in plan.rows] == ["skipped:frozen"] and plan.selected == ()


def test_the_phishing_mint_is_never_touched_even_unfrozen_empty_and_clean() -> None:
    """Security review (28/09): freeze and balance are the issuer's to change.
    Unfrozen and burned to zero via a permanent delegate, the account would read
    initialized / 0 / immutableOwner / ATA — ``classify`` alone says ``close``."""
    clean = phishing_raw(amount=0, state="initialized")
    base = build_plan(rows(clean), wallet=WALLET, limit=None, token_2022=True)
    assert [v for _, v in base.rows] == ["close"]  # the hole the fixed set closes
    plan = rules.judge(rows(clean), wallet=WALLET, recognized=frozenset())
    assert verdicts(plan)[PHISHING_MINT] == "skipped:never_touch:phishing"
    assert plan.selected == () and rules.batches(plan) == ()


def test_refresh_drops_a_never_touch_row_even_if_it_reached_a_batch() -> None:
    clean = rows(phishing_raw(amount=0, state="initialized"))
    fresh = build_plan(clean, wallet=WALLET, limit=None, token_2022=True)  # says close
    kept, dropped = rules.refresh_batch(clean, fresh)
    assert kept == () and [why for _, why in dropped] == ["dropped:never_touch:phishing"]


def test_a_nonzero_balance_is_skipped_even_by_one_atom() -> None:
    plan = rules.judge(rows(raw_account(1, amount=1)), wallet=WALLET, recognized=frozenset())
    assert [v for _, v in plan.rows] == ["skipped:nonzero_balance"]


def test_a_mint_the_executor_recognizes_is_kept() -> None:
    empty = raw_account(1)
    mint = empty["account"]["data"]["parsed"]["info"]["mint"]
    plan = rules.judge(rows(empty), wallet=WALLET, recognized=frozenset({mint}))
    assert verdicts(plan)[mint] == "skipped:recognized_mint"
    assert plan.selected == ()


def test_the_wsol_and_usdc_accounts_are_kept_even_when_empty() -> None:
    wsol = raw_account(1, mint=WSOL, native=True)
    usdc = raw_account(2, mint=USDC)
    plan = rules.judge(rows(wsol, usdc), wallet=WALLET, recognized=frozenset())
    assert verdicts(plan) == {
        WSOL: "skipped:kept_quote_mint:wsol",
        USDC: "skipped:kept_quote_mint:usdc",
    }
    assert plan.selected == ()


def test_the_quote_mints_are_the_executors_own() -> None:
    assert frozenset(rules.KEPT_QUOTE_MINTS) == wallet_holdings.QUOTE_MINTS


def test_a_token_2022_account_with_withheld_transfer_fees_is_skipped() -> None:
    extensions = [{"extension": "immutableOwner"}, {"extension": "transferFeeAmount"}]
    raw = raw_account(1, program=TOKEN_2022_PROGRAM_ID, extensions=extensions, space=178)
    plan = rules.judge(rows(raw), wallet=WALLET, recognized=frozenset())
    assert [v for _, v in plan.rows] == ["skipped:token_2022_extension:transferFeeAmount"]


def test_a_foreign_close_authority_is_skipped() -> None:
    plan = rules.judge(
        rows(raw_account(1, close_authority=PHISHING_MINT)), wallet=WALLET, recognized=frozenset()
    )
    assert [v for _, v in plan.rows] == ["skipped:authority_mismatch"]


def test_a_physical_skip_is_not_relabelled_by_policy() -> None:
    """A recognized mint with a balance stays ``nonzero_balance``: the chain fact wins."""
    raw = raw_account(1, amount=5)
    mint = raw["account"]["data"]["parsed"]["info"]["mint"]
    plan = rules.judge(rows(raw), wallet=WALLET, recognized=frozenset({mint}))
    assert verdicts(plan)[mint] == "skipped:nonzero_balance"


# --- listing envelope (Astra must-fix 1)


class _ListingRpc:
    def __init__(self, token_2022_result: Any) -> None:
        self.token_2022_result = token_2022_result

    def call(self, method: str, params: list[Any]) -> Any:
        if params[1]["programId"] == TOKEN_PROGRAM_ID:
            return {"value": [raw_account(1)]}
        if isinstance(self.token_2022_result, Exception):
            raise self.token_2022_result
        return self.token_2022_result


@pytest.mark.parametrize(
    "answer", [{"value": {}}, {"value": None}, {}, None, TimeoutError("rpc timed out")]
)
def test_a_partial_or_failed_listing_is_refused_never_read_as_empty(answer: Any) -> None:
    with pytest.raises(rules.Refused) as refused:
        rules.list_accounts(_ListingRpc(answer), WALLET)
    assert refused.value.reason.startswith("chain_read_failed:")


def test_a_well_formed_listing_reads_both_programs() -> None:
    listed = rules.list_accounts(_ListingRpc({"value": [phishing_raw()]}), WALLET)
    assert [row.program for row in listed] == [TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID]


# --- batches


def the_28_09_wallet() -> tuple[Any, ...]:
    classic = [raw_account(i) for i in range(5)]
    t22 = [
        raw_account(10 + i, program=TOKEN_2022_PROGRAM_ID, lamports=RENT_2022) for i in range(75)
    ]
    return rows(*classic, *t22, phishing_raw())


def test_the_28_09_wallet_cuts_into_eleven_homogeneous_batches_without_the_phishing_one() -> None:
    plan = rules.judge(the_28_09_wallet(), wallet=WALLET, recognized=frozenset())
    parts = rules.batches(plan)
    assert [len(p) for p in parts] == [5] + [8] * 9 + [3]
    assert all(len({row.program for row in part}) == 1 for part in parts)
    assert all(row.mint != PHISHING_MINT for part in parts for row in part)
    assert plan.total_recoverable == 5 * RENT + 75 * RENT_2022


def test_a_full_batch_fits_a_transaction_and_refunds_only_the_wallet() -> None:
    plan = rules.judge(the_28_09_wallet(), wallet=WALLET, recognized=frozenset())
    batch = rules.batches(plan)[1]
    message = build_batch_message(
        wallet=WALLET,
        accounts=[row.address for row in batch],
        blockhash=BLOCKHASH,
        priority_fee_lamports=10_000,
        token_program=TOKEN_2022_PROGRAM_ID,
    )
    size = len(serialize_transaction((bytes(64),), serialize_message(message)))
    assert size <= rules.TX_SIZE_LIMIT
    closed = verify_close_atas_message(
        message, wallet=WALLET, allowed_accounts={row.address: row.program for row in batch}
    )
    assert closed == tuple(row.address for row in batch)


def test_estimated_fees_and_net() -> None:
    plan = rules.judge(the_28_09_wallet(), wallet=WALLET, recognized=frozenset())
    fee = rules.estimated_fee_lamports(n_batches=11, priority_fee_lamports=10_000)
    assert fee == 11 * (5_000 + 10_000)
    report = rules.format_report(plan, priority_fee_lamports=10_000, max_batches=None)
    assert f"estimated_fee_lamports={fee}" in report
    assert f"expected_net_lamports={plan.total_recoverable - fee}" in report
    assert "total_recoverable_sol=0.123" in report  # Decimal, 9 places
    assert PHISHING_MINT in report and "skipped:never_touch:phishing" in report


# --- TOCTOU


def test_refresh_keeps_unchanged_rows_and_drops_each_change_by_name() -> None:
    raws = [raw_account(i) for i in range(4)]
    first = rules.judge(rows(*raws), wallet=WALLET, recognized=frozenset())
    batch = rules.batches(first)[0]
    mint_3 = raws[3]["account"]["data"]["parsed"]["info"]["mint"]
    now = rows(
        raws[0],
        raw_account(1, amount=7),  # got a deposit
        # raws[2] is gone (closed by someone else)
        raws[3],
    )
    fresh = rules.judge(now, wallet=WALLET, recognized=frozenset({mint_3}))  # now recognized
    kept, dropped = rules.refresh_batch(batch, fresh)
    assert kept == (batch[0],)
    assert [reason for _, reason in dropped] == [
        "dropped:account_changed",
        "dropped:account_gone",
        "dropped:skipped:recognized_mint",
    ]


# --- audit row


class RecordingSession:
    def __init__(self) -> None:
        self.statements: list[tuple[str, dict[str, Any]]] = []
        self.commits = 0

    async def execute(self, statement: Any, parameters: Any = None, /) -> Any:
        self.statements.append((str(statement), dict(parameters or {})))

    async def commit(self) -> None:
        self.commits += 1


async def test_the_audit_row_is_system_scope_and_carries_who_what_and_the_note() -> None:
    session = RecordingSession()
    proof = NoteProof(path="obsidian/x.md", sha256="a" * 64, git_blob_sha=None)
    await rules.write_audit(
        session,
        action=rules.ACTION_BATCH,
        after={"wallet": WALLET, "signature": "sig", "accounts": ["A"], "lamports_recovered": 1},
        actor="everton",
        reason="aluguel",
        proof=proof,
    )
    assert session.commits == 1
    [(sql, params)] = session.statements
    assert sql.startswith("INSERT INTO audit_logs")
    assert "NULL, 'system', NULL" in sql  # organization_id, actor_type, actor_id
    assert params["action"] == "wallet.close_empty_token_accounts.batch"
    after = json.loads(params["after"])
    assert after["signature"] == "sig" and after["accounts"] == ["A"]
    meta = json.loads(params["metadata"])
    assert meta["actor_input"] == "everton" and meta["reason"] == "aluguel"
    assert meta["note"] == "obsidian/x.md" and meta["note_sha256"] == "a" * 64
    assert meta["script"] == "infra/scripts/close_empty_token_accounts.py"


# --- the in-flight SQL stays the executor's


def test_in_flight_statuses_are_the_ones_the_executor_uses() -> None:
    recognized_sql = str(wallet_holdings._RECOGNIZED)  # pyright: ignore[reportPrivateUsage]
    listed = ", ".join(f"'{s}'" for s in rules.IN_FLIGHT_STATUSES)
    assert recognized_sql.count(f"IN ({listed})") == 2
    sql = str(rules.IN_FLIGHT_SQL)
    assert sql.count(f"IN ({listed})") == 2
    assert "meme_live_orders" in sql and "spot_orders" in sql and sql.count("side = 'buy'") == 2


# --- note gate


def _note(tmp_path: Path, body: str) -> str:
    (tmp_path / "obsidian").mkdir(exist_ok=True)
    (tmp_path / "obsidian" / "n.md").write_text(body, encoding="utf-8")
    return "obsidian/n.md"


@pytest.mark.parametrize("body", ["rodar close_empty_token_accounts hoje", f"carteira {WALLET}"])
def test_the_note_must_name_the_tool_or_the_wallet(tmp_path: Path, body: str) -> None:
    proof = rules.require_note(_note(tmp_path, body), wallet=WALLET, repo_root=tmp_path)
    assert proof.path == "obsidian/n.md"


@pytest.mark.parametrize("note", [None, "obsidian/n.md", "docs/n.md"])
def test_a_missing_or_unrelated_note_is_refused_by_name(tmp_path: Path, note: str | None) -> None:
    _note(tmp_path, "uma nota sobre outra coisa")
    with pytest.raises(rules.Refused) as refused:
        rules.require_note(note, wallet=WALLET, repo_root=tmp_path)
    assert refused.value.reason.startswith("note_")
