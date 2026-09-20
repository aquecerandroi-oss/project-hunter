"""T4.77b — ``--token-2022``: closing the desk's EMPTY Token-2022 token
accounts (the 35 pump.fun ATAs, ``immutableOwner`` only, 1 513 840 lamports
each) under the guards Astra demanded in the T4.77 review. Every guard has a
passing and a failing case here; without the flag the plan, the verifier and
the CLI behave exactly as ``test_meme_close_atas*.py`` already prove.
No network, no key, no database.
"""

from __future__ import annotations

import asyncio
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

import meme_close_atas as script  # noqa: E402
import meme_close_atas_send as send  # noqa: E402
from meme_close_atas_plan import (  # noqa: E402
    TokenAccountRow,
    batches,
    build_batch_message,
    build_plan,
    classify,
    format_table,
    parse_token_accounts,
)
from meme_close_atas_verify import CloseAtasRefused, verify_close_atas_message  # noqa: E402
from test_meme_close_atas import FakeRpc as ListingRpc  # noqa: E402
from test_meme_close_atas import (  # noqa: E402
    _Batches,  # pyright: ignore[reportPrivateUsage]
    _KillSwitch,  # pyright: ignore[reportPrivateUsage]
)
from test_meme_close_atas_plan import BLOCKHASH, OTHER, RENT, WALLET, raw_account  # noqa: E402
from test_meme_close_atas_send import SIGNATURE, FakeConn, FakeSigner  # noqa: E402
from test_meme_close_atas_send import FakeRpc as SendRpc  # noqa: E402

from hunter_core.domain.enums import KillSwitchState  # noqa: E402
from hunter_exchanges.pumpfun.solana_codec import (  # noqa: E402
    TOKEN_2022_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
    AccountMeta,
    Instruction,
    associated_token_address,
    b58encode,
    compile_message,
    decompile_message,
    deserialize_message,
    set_compute_unit_limit,
    set_compute_unit_price,
)

RENT_2022 = 1_513_840
T22 = TOKEN_2022_PROGRAM_ID
CLOSE = bytes([9])
NO_EXTENSIONS: list[dict[str, Any]] = []


def _ata(i: int, program: str = TOKEN_PROGRAM_ID) -> str:
    """The real ATA of (wallet, mint i) — the program is part of the seeds."""
    return associated_token_address(
        WALLET, b58encode(bytes([0x10 + i]) * 32), token_program=program
    )


def _row(i: int, **kw: Any) -> TokenAccountRow:
    kw.setdefault("program", T22)
    kw.setdefault("lamports", RENT_2022)
    (row,) = parse_token_accounts([raw_account(i, **kw)], program=kw["program"])
    return row


def _classic(i: int, **kw: Any) -> TokenAccountRow:
    (row,) = parse_token_accounts([raw_account(i, **kw)], program=TOKEN_PROGRAM_ID)
    return row


# --- parsing: the jsonParsed shape of a Token-2022 account (agave account-decoder)


def test_parse_reads_the_type_and_the_extension_names_of_a_token_2022_row() -> None:
    row = _row(1)
    assert row.program == T22
    assert row.kind == "account"
    assert row.extensions == ("immutableOwner",)
    assert row.lamports == RENT_2022
    assert row.address == _ata(1, T22)
    assert _classic(1).extensions == ()


def test_parse_refuses_an_extension_entry_without_a_name() -> None:
    with pytest.raises(ValueError, match="unparsable"):
        parse_token_accounts([raw_account(1, program=T22, extensions=[{"state": {}}])], program=T22)


def test_parse_refuses_a_row_without_a_parsed_type() -> None:
    broken = raw_account(1, program=T22)
    del broken["account"]["data"]["parsed"]["type"]
    with pytest.raises(ValueError, match="unparsable"):
        parse_token_accounts([broken], program=T22)


# --- classify: the Token-2022 guard table (Astra, T4.77 review, item 1)


def test_without_the_flag_a_token_2022_account_is_still_only_listed() -> None:
    assert classify(_row(1), wallet=WALLET) == "skipped:token_2022"
    assert classify(_row(1), wallet=WALLET, token_2022=False) == "skipped:token_2022"


TOKEN_2022_CASES: list[tuple[dict[str, Any], str]] = [
    ({}, "close"),
    ({"extensions": NO_EXTENSIONS, "space": 165}, "close"),
    ({"close_authority": WALLET}, "close"),
    ({"kind": "mint"}, "skipped:not_token_account:mint"),
    ({"kind": "multisig"}, "skipped:not_token_account:multisig"),
    ({"amount": 1}, "skipped:nonzero_balance"),
    ({"state": "frozen"}, "skipped:frozen"),
    ({"owner": OTHER}, "skipped:authority_mismatch"),
    ({"delegate": OTHER}, "skipped:authority_mismatch"),
    ({"close_authority": OTHER}, "skipped:authority_mismatch"),
    (
        {
            "extensions": [
                {"extension": "immutableOwner"},
                {"extension": "transferFeeAmount", "state": {"withheldAmount": 0}},
            ]
        },
        "skipped:token_2022_extension:transferFeeAmount",
    ),
    (
        {"extensions": [{"extension": "confidentialTransferAccount", "state": {}}]},
        "skipped:token_2022_extension:confidentialTransferAccount",
    ),
    (
        {"extensions": [{"extension": "memoTransfer", "state": {}}]},
        "skipped:token_2022_extension:memoTransfer",
    ),
    (
        {"extensions": [{"extension": "cpiGuard", "state": {"lockCpi": True}}]},
        "skipped:token_2022_extension:cpiGuard",
    ),
    (
        {"extensions": [{"extension": "permanentDelegate", "state": {"delegate": OTHER}}]},
        "skipped:token_2022_extension:permanentDelegate",
    ),
    (
        {"extensions": [{"extension": "transferHookAccount", "state": {}}]},
        "skipped:token_2022_extension:transferHookAccount",
    ),
    (
        {"extensions": [{"extension": "unparseableExtension"}]},
        "skipped:token_2022_extension:unparseableExtension",
    ),
    ({"lamports": 0}, "skipped:no_rent"),
]


@pytest.mark.parametrize(("kw", "verdict"), TOKEN_2022_CASES)
def test_the_token_2022_verdict_table(kw: dict[str, Any], verdict: str) -> None:
    assert classify(_row(1, **kw), wallet=WALLET, token_2022=True) == verdict


def test_a_token_2022_account_must_be_the_ata_derived_with_token_2022_in_the_seeds() -> None:
    # the classic-program ATA address of the same (wallet, mint) is NOT the Token-2022 ATA
    wrong_seed = _row(1, pubkey=_ata(1, TOKEN_PROGRAM_ID))
    assert classify(wrong_seed, wallet=WALLET, token_2022=True) == "skipped:not_ata"
    stray = _row(1, pubkey=b58encode(bytes([0x66]) * 32))
    assert classify(stray, wallet=WALLET, token_2022=True) == "skipped:not_ata"
    assert classify(_row(1), wallet=WALLET, token_2022=True) == "close"


@pytest.mark.parametrize(
    ("kw", "verdict"),
    [
        ({"space": 170}, "close"),
        ({"space": 165, "extensions": NO_EXTENSIONS}, "close"),
        ({"space": 170, "extensions": NO_EXTENSIONS}, "skipped:space_mismatch:170"),
        ({"space": 174}, "skipped:space_mismatch:174"),
        ({"space": 200}, "skipped:space_mismatch:200"),
        ({"space": 165}, "skipped:space_mismatch:165"),
    ],
)
def test_the_on_chain_size_must_match_the_declared_extensions(
    kw: dict[str, Any], verdict: str
) -> None:
    """Astra (T4.77b re-review, MUST-FIX): the account decoder enumerates the
    TLV with ``get_extension_types().unwrap_or_default()`` — an extension the
    RPC's decoder does not know makes the list come back EMPTY, not
    ``unparseableExtension``. ``space`` is the on-chain data length, which
    the decoder cannot shrink: an undeclared extension is always extra bytes."""
    assert classify(_row(1, **kw), wallet=WALLET, token_2022=True) == verdict


def test_a_row_without_a_space_field_is_unparsable() -> None:
    broken = raw_account(1, program=T22)
    del broken["account"]["space"]
    del broken["account"]["data"]["space"]
    with pytest.raises(ValueError, match="unparsable"):
        parse_token_accounts([broken], program=T22)
    only_in_data = raw_account(1, program=T22)
    del only_in_data["account"]["space"]
    (row,) = parse_token_accounts([only_in_data], program=T22)
    assert row.space == 170


def test_the_classic_verdicts_do_not_change_when_the_flag_is_on() -> None:
    assert classify(_classic(1), wallet=WALLET, token_2022=True) == "close"
    assert classify(_classic(1, amount=1), wallet=WALLET, token_2022=True) == (
        "skipped:nonzero_balance"
    )
    assert classify(_classic(1, kind="mint"), wallet=WALLET) == "skipped:not_token_account:mint"
    assert classify(_classic(1, space=170), wallet=WALLET) == "skipped:space_mismatch:170"


# --- plan: the program is recorded per account; batches are homogeneous (item 2)


def test_the_plan_records_the_program_per_account_and_batches_never_mix_programs() -> None:
    rows = [_classic(0), _row(1), _classic(2), *[_row(i) for i in range(3, 13)]]
    plan = build_plan(rows, wallet=WALLET, limit=None, token_2022=True)
    assert [v for _, v in plan.rows] == ["close"] * 13
    assert plan.total_recoverable == 2 * RENT + 11 * RENT_2022
    parts = batches(plan)
    assert [(len(p), {r.program for r in p}) for p in parts] == [
        (2, {TOKEN_PROGRAM_ID}),
        (8, {T22}),
        (3, {T22}),
    ]
    assert [r.program for r in plan.selected].count(T22) == 11


def test_without_the_flag_the_plan_is_exactly_the_old_one() -> None:
    rows = [_classic(0), _row(1), _classic(2)]
    plan = build_plan(rows, wallet=WALLET, limit=None)
    assert [v for _, v in plan.rows] == ["close", "skipped:token_2022", "close"]
    assert [len(p) for p in batches(plan)] == [2]
    assert "token_2022_rent_not_touched_lamports=1513840" in format_table(plan)


def test_the_table_names_the_program_of_every_row() -> None:
    text = format_table(
        build_plan([_classic(0), _row(1)], wallet=WALLET, limit=None, token_2022=True)
    )
    lines = text.splitlines()
    assert "program" in lines[0]
    assert "token-2022" in lines[2] and lines[2].rstrip().endswith("close")
    assert "token " in lines[1] and "token-2022" not in lines[1]
    assert "token_2022_rent_not_touched" not in text


def test_the_proof_run_selects_at_most_one_token_2022_account_and_defers_the_classic_ones() -> None:
    """Item 4: the first real run closes ONE Token-2022 account, so the
    operator proves the close on mainnet before the batches of 8."""
    rows = [_classic(0), *[_row(i) for i in range(1, 6)]]
    plan = build_plan(rows, wallet=WALLET, limit=1, token_2022=True, proof_run=True)
    assert [v for _, v in plan.rows] == ["skipped:proof_run_token_2022_only", *["close"] * 5]
    assert [r.address for r in plan.selected] == [_ata(1, T22)]
    assert [len(p) for p in batches(plan)] == [1]
    with pytest.raises(ValueError, match="proof_run_requires_token_2022"):
        build_plan(rows, wallet=WALLET, limit=1, proof_run=True)


# --- the batch message carries the program the batch is for


def test_the_batch_message_for_token_2022_targets_the_token_2022_program() -> None:
    accounts = tuple(_ata(i, T22) for i in range(3))
    message = build_batch_message(
        wallet=WALLET,
        accounts=accounts,
        blockhash=BLOCKHASH,
        priority_fee_lamports=10_000,
        token_program=T22,
    )
    closes = decompile_message(message)[2:]
    assert [ix.program_id for ix in closes] == [T22] * 3
    assert [ix.data for ix in closes] == [CLOSE] * 3
    with pytest.raises(ValueError, match="token_program_not_allowed"):
        build_batch_message(
            wallet=WALLET,
            accounts=accounts,
            blockhash=BLOCKHASH,
            priority_fee_lamports=1,
            token_program=OTHER,
        )


# --- verifier (item 3): the program of every CloseAccount must be the plan's


def _close(program: str, account: str, *, data: bytes = CLOSE, extra: bool = False) -> Instruction:
    metas = [
        AccountMeta(account, False, True),
        AccountMeta(WALLET, False, True),
        AccountMeta(WALLET, True, False),
    ]
    if extra:
        metas.append(AccountMeta(OTHER, False, False))
    return Instruction(program, tuple(metas), data)


def _budget() -> list[Instruction]:
    return [set_compute_unit_limit(50_000), set_compute_unit_price(200_000)]


A22 = tuple(_ata(i, T22) for i in range(8))
ACLASSIC = tuple(_ata(i) for i in range(8))
PLAN = {**{a: T22 for a in A22}, **{a: TOKEN_PROGRAM_ID for a in ACLASSIC}}


def _verify(instructions: list[Instruction]) -> tuple[str, ...]:
    message = compile_message(WALLET, instructions, BLOCKHASH)
    return verify_close_atas_message(message, wallet=WALLET, allowed_accounts=PLAN)


def test_a_token_2022_close_of_an_account_the_plan_listed_as_token_2022_verifies() -> None:
    assert _verify([*_budget(), _close(T22, A22[0]), _close(T22, A22[1])]) == A22[:2]
    message = build_batch_message(
        wallet=WALLET,
        accounts=A22,
        blockhash=BLOCKHASH,
        priority_fee_lamports=10_000,
        token_program=T22,
    )
    assert verify_close_atas_message(message, wallet=WALLET, allowed_accounts=PLAN) == A22


def test_a_token_2022_close_of_an_account_the_plan_listed_as_classic_is_refused() -> None:
    with pytest.raises(CloseAtasRefused, match="close_account_program_mismatch"):
        _verify([*_budget(), _close(T22, ACLASSIC[0])])


def test_a_classic_close_of_an_account_the_plan_listed_as_token_2022_is_refused() -> None:
    with pytest.raises(CloseAtasRefused, match="close_account_program_mismatch"):
        _verify([*_budget(), _close(TOKEN_PROGRAM_ID, A22[0])])


def test_a_token_2022_close_with_four_accounts_is_refused() -> None:
    with pytest.raises(CloseAtasRefused, match="close_account_accounts_not_three"):
        _verify([*_budget(), _close(T22, A22[0], extra=True)])


@pytest.mark.parametrize("data", [bytes([3]) + bytes(8), bytes([9, 0]), bytes([26]), b""])
def test_a_token_2022_instruction_whose_data_is_not_exactly_0x09_is_refused(data: bytes) -> None:
    with pytest.raises(CloseAtasRefused, match="token_instruction_not_close_account"):
        _verify([*_budget(), _close(T22, A22[0], data=data)])


def test_a_message_mixing_the_two_programs_is_refused_even_when_every_close_matches() -> None:
    with pytest.raises(CloseAtasRefused, match="batch_programs_mixed"):
        _verify([*_budget(), _close(TOKEN_PROGRAM_ID, ACLASSIC[0]), _close(T22, A22[0])])


def test_a_token_2022_close_not_in_the_plan_at_all_is_refused() -> None:
    with pytest.raises(CloseAtasRefused, match="close_account_not_in_plan"):
        _verify([*_budget(), _close(T22, b58encode(bytes([0x55]) * 32))])


# --- send path: the batch's program drives the builder and the audit row


def _send_batch(rows: list[TokenAccountRow]) -> tuple[send.BatchResult, FakeConn, SendRpc]:
    rent = sum(r.lamports for r in rows)
    landed = 500_000_000 + rent - send.BASE_FEE_LAMPORTS - 10_000
    rpc = SendRpc(
        statuses=[{"confirmationStatus": "confirmed", "err": None}],
        sim_lamports=landed,
        landed=landed,
        tx_meta={
            "transaction": {"message": {"accountKeys": [WALLET, "x"]}},
            "meta": {
                "err": None,
                "fee": 15_000,
                "preBalances": [500_000_000, rent],
                "postBalances": [landed, 0],
            },
        },
    )
    conn = FakeConn()
    interval = send.CONFIRM_INTERVAL_S
    send.CONFIRM_INTERVAL_S = 0.0
    try:
        result = asyncio.run(
            send.run_batch(
                conn,
                rpc,
                FakeSigner(),
                batch=rows,
                reason="T4.77b prova",
                actor="everton",
                priority_fee_lamports=10_000,
            )
        )
    finally:
        send.CONFIRM_INTERVAL_S = interval
    return result, conn, rpc


def test_a_token_2022_batch_is_built_for_token_2022_verified_simulated_and_audited() -> None:
    result, conn, rpc = _send_batch([_row(1), _row(2)])
    assert result.status == "confirmed" and result.n_closed == 2
    assert result.expected_rent == 2 * RENT_2022
    assert result.lamports_recovered == 2 * RENT_2022 - send.BASE_FEE_LAMPORTS - 10_000
    closes = decompile_message(deserialize_message(rpc.sent[0][65:]))[2:]
    assert [ix.program_id for ix in closes] == [T22, T22]
    assert [e["event"] for e in conn.events] == ["close_atas_submitted", "close_atas_confirmed"]
    assert conn.events[0]["data"]["token_program"] == T22
    assert conn.events[1]["data"]["token_program"] == T22


def test_a_batch_mixing_programs_is_refused_before_anything_is_built_or_signed() -> None:
    result, conn, rpc = _send_batch([_classic(0), _row(1)])
    assert result.status == "refused" and result.reason == "batch_programs_mixed"
    assert rpc.sent == [] and "simulate" not in rpc.log
    assert [e["event"] for e in conn.events] == ["close_atas_refused"]


# --- CLI: the flag, the proof run, --i-know-2022


class Rpc2022(ListingRpc):
    """Two classic empties + N Token-2022 empties (immutableOwner only)."""

    def __init__(self, *, empty: int = 2, token_2022: int = 35) -> None:
        super().__init__(empty=empty, dust=0, token_2022=token_2022)

    def call(self, method: str, params: list[Any]) -> Any:
        assert method == "getTokenAccountsByOwner"
        self.calls.append(params[0])
        if params[1]["programId"] == TOKEN_PROGRAM_ID:
            value = [raw_account(i) for i in range(self.empty)]
        else:
            value = [
                raw_account(100 + i, program=T22, lamports=RENT_2022)
                for i in range(self.token_2022)
            ]
        return {"context": {"slot": 1}, "value": value}


def _patch(monkeypatch: pytest.MonkeyPatch, rpc: Rpc2022) -> None:
    def _client(url: str, **kw: Any) -> Rpc2022:
        return rpc

    monkeypatch.setattr(script, "SolanaTxRpcClient", _client)


def test_dry_run_without_the_flag_is_unchanged(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch(monkeypatch, Rpc2022())
    assert script.main(["--user", WALLET]) == 0
    out = capsys.readouterr().out
    assert out.count("skipped:token_2022") == 35
    assert "selected=2" in out and f"total_recoverable_lamports={2 * RENT}" in out
    assert "token_2022_rent_not_touched_lamports=52984400" in out
    assert "proof_run" not in out


def test_dry_run_with_the_flag_is_a_proof_run_of_one_token_2022_account(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch(monkeypatch, Rpc2022())
    assert script.main(["--user", WALLET, "--token-2022"]) == 0
    out = capsys.readouterr().out
    assert out.count("  close") == 35
    assert out.count("skipped:proof_run_token_2022_only") == 2
    assert "selected=1" in out and f"total_recoverable_lamports={RENT_2022}" in out
    assert "batches=1 batch_size=8 this_run_max_batches=1 accounts_this_run=1" in out
    assert "proof_run=token_2022" in out and "--i-know-2022" in out
    assert "dry-run: nothing written (add --apply)" in out


def test_dry_run_with_i_know_2022_plans_every_account_in_homogeneous_batches(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch(monkeypatch, Rpc2022())
    assert (
        script.main(["--user", WALLET, "--token-2022", "--i-know-2022", "--max-batches", "6"]) == 0
    )
    out = capsys.readouterr().out
    assert out.count("  close") == 37
    assert "selected=37" in out
    assert f"total_recoverable_lamports={2 * RENT + 35 * RENT_2022}" in out
    # [2 classic], then 35 Token-2022 in 8+8+8+8+3
    assert "batches=6 batch_size=8 this_run_max_batches=6 accounts_this_run=37" in out
    assert "proof_run" not in out


@pytest.mark.parametrize(
    "argv",
    [
        ["--user", WALLET, "--i-know-2022"],
        ["--user", WALLET, "--token-2022", "--limit", "5"],
        ["--user", WALLET, "--token-2022", "--max-batches", "2"],
    ],
)
def test_usage_errors_of_the_token_2022_flags(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    rpc = Rpc2022()
    _patch(monkeypatch, rpc)
    assert script.main(argv) == script.EX_USAGE
    assert "usage:" in capsys.readouterr().err
    assert rpc.calls == []


def _run_apply(
    monkeypatch: pytest.MonkeyPatch, argv: list[str], runner: _Batches, rpc: Rpc2022
) -> int:
    monkeypatch.setattr(
        script, "read_effective_kill_switch_state", _KillSwitch(KillSwitchState.ACTIVE)
    )
    monkeypatch.setattr(script, "run_batch", runner)
    args = script.parse_args(["--apply", *argv])
    load_signer: Any = FakeSigner
    return asyncio.run(
        script.apply_with(args, conn=object(), redis=object(), rpc=rpc, load_signer=load_signer)
    )


def test_apply_with_the_flag_runs_exactly_one_token_2022_close_the_first_time(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = _Batches(send.BatchResult("confirmed", SIGNATURE, 1, RENT_2022 - 15_000, RENT_2022))
    code = _run_apply(monkeypatch, ["--token-2022", "--max-batches", "1"], runner, Rpc2022())
    assert code == 0
    assert len(runner.calls) == 1
    (batch,) = [c["batch"] for c in runner.calls]
    assert len(batch) == 1 and batch[0].program == T22
    out = capsys.readouterr().out
    line = json.loads(next(ln for ln in out.splitlines() if ln.startswith("{")))
    assert line["n_closed"] == 1
    assert "proof_run=token_2022" in out


def test_apply_with_i_know_2022_runs_the_batches_in_program_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def confirmed(n: int, rent: int) -> send.BatchResult:
        return send.BatchResult("confirmed", SIGNATURE, n, n * rent - 15_000, n * rent)

    runner = _Batches(confirmed(2, RENT), confirmed(8, RENT_2022), confirmed(2, RENT_2022))
    code = _run_apply(
        monkeypatch,
        ["--token-2022", "--i-know-2022", "--max-batches", "3"],
        runner,
        Rpc2022(token_2022=10),
    )
    assert code == 0
    programs = [{r.program for r in c["batch"]} for c in runner.calls]
    assert programs == [{TOKEN_PROGRAM_ID}, {T22}, {T22}]
    assert [len(c["batch"]) for c in runner.calls] == [2, 8, 2]


def test_apply_without_the_flag_never_hands_a_token_2022_account_to_the_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _Batches(send.BatchResult("confirmed", SIGNATURE, 2, 2 * RENT - 15_000, 2 * RENT))
    assert _run_apply(monkeypatch, ["--max-batches", "5"], runner, Rpc2022()) == 0
    assert len(runner.calls) == 1
    assert {r.program for r in runner.calls[0]["batch"]} == {TOKEN_PROGRAM_ID}
