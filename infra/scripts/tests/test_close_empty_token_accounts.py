"""``close_empty_token_accounts.py`` — the dry-run and the ``--apply``
orchestration against the fakes in ``close_empty_token_accounts_rig`` (kill
switch, in-flight SQL, recognized SQL, chain listing, signer, the T4.77 batch
runner, the session). Never a network call, never a key, never a transaction.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
for extra in (SCRIPTS_DIR, SCRIPTS_DIR / "tests"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import close_empty_token_accounts as script  # noqa: E402
import close_empty_token_accounts_rules as rules  # noqa: E402
from close_empty_token_accounts_rig import OTHER, Rig  # noqa: E402
from meme_close_atas_send import BatchResult  # noqa: E402
from test_close_empty_token_accounts_rules import PHISHING_MINT, phishing_raw, rows  # noqa: E402
from test_meme_close_atas_plan import WALLET, raw_account  # noqa: E402

from hunter_core.domain.enums import KillSwitchState  # noqa: E402

# --- dry run


async def test_dry_run_lists_everything_and_signs_sends_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rig = Rig(tmp_path, argv=[])
    args = script.parse_args(rig.argv)
    assert await script.dry_run_with(args, session=rig.session, rpc=None, deps=rig.deps) == 0
    out = capsys.readouterr().out
    assert (
        out.count("  close") == 80
        and f"{PHISHING_MINT}" in out
        and "skipped:never_touch:phishing" in out
    )
    assert "in_flight_buys meme=0 spot=0" in out and "dry-run: nothing signed" in out
    assert "open_positions meme=0 spot=1" in out  # runbook step 2 reads this line
    assert "wallet_balance_lamports=384500000 wallet_balance_sol=0.384500000" in out
    assert rig.signers == 0 and rig.batches.seen == [] and rig.session.audits == []


async def test_an_unreadable_balance_is_said_not_invented(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rig = Rig(tmp_path, argv=[], lamports=TimeoutError("rpc"))
    args = script.parse_args(rig.argv)
    code = await script.dry_run_with(args, session=rig.session, rpc=None, deps=rig.deps)
    captured = capsys.readouterr()
    assert code == script.EX_REFUSED  # runbook step 4 needs the number: said, and not a success
    assert "wallet_balance_lamports=unreadable:TimeoutError" in captured.out
    assert "refused: balance_unreadable" in captured.err


def test_the_dry_run_rpc_client_cannot_send(monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[dict[str, Any]] = []

    def fake_client(url: str, **kw: Any) -> None:
        built.append(kw)

    monkeypatch.setattr(script, "SolanaTxRpcClient", fake_client)
    script.rpc_client(script.parse_args(["--user", WALLET]))
    script.rpc_client(script.parse_args(["--user", WALLET, "--apply"]))
    assert built == [{}, {"allow_send": True}]


async def test_dry_run_refuses_by_name_when_the_db_read_fails(tmp_path: Path) -> None:
    rig = Rig(tmp_path, argv=[], recognized=OSError("db down"))
    with pytest.raises(rules.Refused, match="db_read_failed"):
        await script.dry_run_with(
            script.parse_args(rig.argv), session=rig.session, rpc=None, deps=rig.deps
        )


@pytest.mark.parametrize(
    "argv", [[], ["--user", WALLET, "--priority-fee-lamports", "100001"], ["--user", "short"]]
)
def test_usage_errors_exit_64(argv: list[str]) -> None:
    assert script.main(argv) == script.EX_USAGE


# --- apply: the happy path on the 28/09 wallet


async def test_apply_closes_80_in_11_batches_never_the_phishing_account(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rig = Rig(tmp_path)
    assert await rig.apply() == 0
    assert [len(b) for b in rig.batches.seen] == [5] + [8] * 9 + [3]
    assert all(row.mint != PHISHING_MINT for b in rig.batches.seen for row in b)
    # the signer is loaded after the note; each intent row is committed before its batch
    assert rig.log[:4] == ["load_signer", "audit:intent", "commit", "run_batch:5"]
    assert rig.actions() == ["intent", "batch"] * 11 + ["run"]
    run = rig.run_row()
    assert run["outcome"] == "done" and run["signatures"] == [f"sig{i}" for i in range(1, 12)]
    assert run["kill_switch_state"] == "ACTIVE" and run["wallet"] == WALLET
    batch = rig.session.audits[1]["after"]
    assert batch["signature"] == "sig1" and len(batch["accounts"]) == 5
    assert rig.session.audits[0]["metadata"]["note"] == "obsidian/n.md"
    assert "done: closed=80" in capsys.readouterr().out


async def test_trading_disabled_does_not_block_rent_recovery(tmp_path: Path) -> None:
    rig = Rig(tmp_path, states=[KillSwitchState.TRADING_DISABLED])
    assert await rig.apply() == 0


# --- apply: refusals before anything is signed


@pytest.mark.parametrize(
    ("over", "reason"),
    [
        ({"in_flight": [{"meme": 1, "spot": 0}]}, "buy_in_flight:meme=1,spot=0"),
        ({"in_flight": [{"meme": 0, "spot": 1}]}, "buy_in_flight:meme=0,spot=1"),
        ({"states": [KillSwitchState.EMERGENCY]}, "kill_switch_emergency"),
        ({"states": [RuntimeError("redis")]}, "kill_switch_unreadable"),
        ({"listings": [rules.Refused("chain_read_failed:TimeoutError")]}, "chain_read_failed"),
        ({"recognized": OSError("db down")}, "db_read_failed"),
        ({"argv": ["--apply"]}, "note_required"),
        ({"signer_pubkey": OTHER}, "destination_not_wallet"),
    ],
)
async def test_apply_is_refused_by_name_and_nothing_is_sent(
    tmp_path: Path, over: dict[str, Any], reason: str
) -> None:
    rig = Rig(tmp_path, **over)
    assert await rig.apply() == script.EX_REFUSED
    assert rig.batches.seen == []
    assert rig.run_row()["outcome"].startswith(f"refused:{reason}")
    if reason != "destination_not_wallet":
        assert rig.signers == 0


async def test_nothing_to_close_needs_no_note_and_loads_no_key(tmp_path: Path) -> None:
    rig = Rig(tmp_path, listings=[rows(phishing_raw())], argv=["--apply"])
    assert await rig.apply() == 0
    assert rig.signers == 0 and rig.run_row()["outcome"] == "nothing_to_close"


async def test_a_buy_that_starts_mid_run_stops_the_next_batch(tmp_path: Path) -> None:
    idle = {"meme": 0, "spot": 0}
    rig = Rig(tmp_path, in_flight=[idle, idle, {"meme": 1, "spot": 0}])
    assert await rig.apply() == script.EX_REFUSED
    assert len(rig.batches.seen) == 1


# --- TOCTOU


async def test_an_account_that_changed_since_the_plan_is_dropped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    classic = [raw_account(i) for i in range(3)]
    changed = rows(raw_account(0, amount=3), *classic[1:])
    rig = Rig(tmp_path, listings=[rows(*classic), changed])
    assert await rig.apply() == 0
    assert [row.address for row in rig.batches.seen[0]] == [r.address for r in rows(*classic)[1:]]
    assert "dropped:account_changed" in capsys.readouterr().out


async def test_a_batch_entirely_gone_is_skipped_without_sending(tmp_path: Path) -> None:
    rig = Rig(tmp_path, listings=[rows(raw_account(0)), rows()])
    assert await rig.apply() == 0
    assert rig.batches.seen == [] and rig.actions() == ["run"]


# --- stop on the first batch that is not a clean confirmation


@pytest.mark.parametrize(
    ("results", "code", "outcome"),
    [
        (["failed"], script.EX_FAILED, "stopped:failed"),
        (["submitted"], script.EX_UNCONFIRMED, "stopped:submitted"),
        (["refused"], script.EX_REFUSED, "stopped:refused"),
        # signed AND confirmed, then stopped: never 65 ("nothing signed")
        (["short"], script.EX_STOPPED_AFTER_CONFIRMED, "stopped:recovered_below_expected"),
    ],
)
async def test_the_first_bad_batch_stops_the_run(
    tmp_path: Path, results: list[str], code: int, outcome: str
) -> None:
    rig = Rig(tmp_path, results=results)
    assert await rig.apply() == code
    assert len(rig.batches.seen) == 1 and rig.run_row()["outcome"] == outcome


async def test_an_audit_failure_after_a_send_never_hides_the_signature(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rig = Rig(tmp_path, results=["submitted"], fail_at={1})  # the .batch INSERT fails
    assert await rig.apply() == script.EX_UNCONFIRMED
    captured = capsys.readouterr()
    assert '"signature": "sig1"' in captured.out and "audit_unwritten" in captured.err


async def test_an_aborted_transaction_is_rolled_back_so_the_run_row_still_lands(
    tmp_path: Path,
) -> None:
    """Security review (28/09, reproduced on PG16): the failed ``.batch`` INSERT
    aborts the transaction; without a rollback the ``.run`` row fails too."""
    rig = Rig(tmp_path, fail_at={1})  # batch 0 confirms, its .batch INSERT fails
    assert await rig.apply() == script.EX_STOPPED_AFTER_CONFIRMED
    run = rig.run_row()  # written after the rollback
    assert run["outcome"] == "stopped:audit_unwritten_after_confirmed"
    assert run["signatures"] == ["sig1"] and len(rig.batches.seen) == 1
    assert rig.session.rollbacks >= 1 and not rig.session.aborted


async def test_max_batches_bounds_the_run(tmp_path: Path) -> None:
    rig = Rig(tmp_path, argv=["--apply", "--note", "obsidian/n.md", "--max-batches", "1"])
    assert await rig.apply() == 0
    assert len(rig.batches.seen) == 1


async def test_a_read_failure_inside_the_runner_before_signing_is_a_named_refusal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Astra (diff review): ``get_latest_blockhash``/``getBalance`` time out
    inside ``run_batch`` before anything is signed — nothing can have been sent."""
    rig = Rig(tmp_path)

    async def blockhash_timeout(*args: Any, **kw: Any) -> BatchResult:
        raise TimeoutError("getLatestBlockhash")

    rig.deps = replace(rig.deps, run_batch=blockhash_timeout)
    assert await rig.apply() == script.EX_REFUSED
    run = rig.run_row()
    assert run["outcome"] == "refused:batch_unsent:TimeoutError"
    assert run["batch_in_progress"] is None
    assert "crashed_mid_batch" not in capsys.readouterr().err


async def test_a_crash_after_signing_names_the_batch_that_may_have_been_sent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rig = Rig(tmp_path)

    async def boom(session: Any, rpc: Any, signer: Any, **kw: Any) -> BatchResult:
        signer.sign(b"message")
        raise ConnectionError("db gone after the broadcast")

    rig.deps = replace(rig.deps, run_batch=boom)
    with pytest.raises(ConnectionError):
        await rig.apply()
    run = rig.run_row()
    assert run["outcome"] == "crashed:ConnectionError" and run["batch_in_progress"] == 0
    assert "crashed_mid_batch batch=0" in capsys.readouterr().err
