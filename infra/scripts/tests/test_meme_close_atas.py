"""``meme_close_atas.py`` (T4.77) -- the CLI: the dry-run end to end against
a fake RPC (listing only; the client it builds cannot broadcast), the usage
guards, and the ``--apply`` logic (``apply_with``) against fakes for the kill
switch, the RPC, the signer and the batch runner -- never a real
transaction, never a wallet key. The batch runner's own path is
``test_meme_close_atas_send.py``.
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
from meme_close_atas_send import BatchResult  # noqa: E402
from test_meme_close_atas_plan import RENT, raw_account  # noqa: E402
from test_meme_close_atas_send import SIGNATURE, FakeSigner  # noqa: E402

from hunter_core.domain.enums import KillSwitchState  # noqa: E402
from hunter_exchanges.pumpfun.solana_codec import (  # noqa: E402
    TOKEN_2022_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
)

WALLET = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
OTHER = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"


class FakeRpc:
    """Listing only. Any other method is a test failure: a dry-run must never
    simulate, sign or send; ``apply_with`` reaches those through the batch
    runner, which is replaced here."""

    def __init__(self, *, empty: int = 10, dust: int = 1, token_2022: int = 1) -> None:
        self.empty, self.dust, self.token_2022 = empty, dust, token_2022
        self.calls: list[str] = []
        self.closed = False

    def call(self, method: str, params: list[Any]) -> Any:
        assert method == "getTokenAccountsByOwner"
        self.calls.append(params[0])
        program = params[1]["programId"]
        if program == TOKEN_PROGRAM_ID:
            value = [raw_account(i) for i in range(self.empty)]
            value += [raw_account(50 + i, amount=1) for i in range(self.dust)]
        else:
            value = [
                raw_account(80 + i, program=TOKEN_2022_PROGRAM_ID) for i in range(self.token_2022)
            ]
        return {"context": {"slot": 1}, "value": value}

    def close(self) -> None:
        self.closed = True

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"dry-run must never call rpc.{name}")


def _patch_rpc(monkeypatch: pytest.MonkeyPatch, rpc: FakeRpc) -> list[dict[str, Any]]:
    built: list[dict[str, Any]] = []

    def _client(url: str, **kwargs: Any) -> FakeRpc:
        built.append({"url": url, **kwargs})
        return rpc

    monkeypatch.setattr(script, "SolanaTxRpcClient", _client)
    return built


def test_dry_run_prints_the_table_and_the_total_and_never_builds_a_sending_client(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rpc = FakeRpc()
    built = _patch_rpc(monkeypatch, rpc)
    code = script.main(["--user", WALLET])
    assert code == 0
    out = capsys.readouterr().out
    assert "verdict" in out
    assert out.count("  close") == 10
    assert "skipped:nonzero_balance" in out and "skipped:token_2022" in out
    assert f"total_recoverable_lamports={10 * RENT}" in out
    assert "batches=2 batch_size=8 this_run_max_batches=1 accounts_this_run=8" in out
    assert "dry-run: nothing written (add --apply)" in out
    assert built == [{"url": script.MAINNET_PUBLIC_RPC_URL}]  # no allow_send
    assert rpc.calls == [WALLET, WALLET] and rpc.closed


def test_dry_run_honours_limit_and_max_batches_in_the_summary(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_rpc(monkeypatch, FakeRpc(empty=20))
    assert script.main(["--user", WALLET, "--limit", "10", "--max-batches", "2"]) == 0
    out = capsys.readouterr().out
    assert "selected=10" in out and "listed=22" in out
    assert "batches=2 batch_size=8 this_run_max_batches=2 accounts_this_run=10" in out


@pytest.mark.parametrize(
    "argv",
    [
        [],  # dry-run without --user
        ["--user", WALLET, "--max-batches", "0"],
        ["--user", WALLET, "--limit", "0"],
        ["--user", WALLET, "--priority-fee-lamports", "100001"],
        ["--user", WALLET, "--priority-fee-lamports", "-1"],
    ],
)
def test_usage_errors_exit_64_before_any_rpc(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    rpc = FakeRpc()
    _patch_rpc(monkeypatch, rpc)
    assert script.main(argv) == script.EX_USAGE
    assert "usage:" in capsys.readouterr().err
    assert rpc.calls == []


# --- apply_with against fakes


class _KillSwitch:
    def __init__(self, *states: KillSwitchState) -> None:
        self.states = list(states)
        self.calls = 0

    async def __call__(self, conn: Any, redis: Any) -> KillSwitchState:
        self.calls += 1
        return self.states[min(self.calls - 1, len(self.states) - 1)]


class _Batches:
    def __init__(self, *results: BatchResult) -> None:
        self.results = list(results)
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, conn: Any, rpc: Any, signer: Any, **kw: Any) -> BatchResult:
        self.calls.append({"signer": signer, **kw})
        return self.results[len(self.calls) - 1]


def _never_load_signer() -> Any:
    raise AssertionError("the signer must not be loaded before the kill switch is read")


def _args(*argv: str) -> Any:
    return script.parse_args(["--apply", *argv])


def _run_apply(
    monkeypatch: pytest.MonkeyPatch,
    *,
    args: Any,
    kill: _KillSwitch,
    runner: _Batches,
    rpc: FakeRpc | None = None,
    load_signer: Any = FakeSigner,
) -> int:
    monkeypatch.setattr(script, "read_effective_kill_switch_state", kill)
    monkeypatch.setattr(script, "run_batch", runner)
    return asyncio.run(
        script.apply_with(
            args, conn=object(), redis=object(), rpc=rpc or FakeRpc(), load_signer=load_signer
        )
    )


def _confirmed(n: int) -> BatchResult:
    return BatchResult("confirmed", SIGNATURE, n, n * RENT - 15_000, n * RENT)


def test_apply_refuses_unless_the_kill_switch_is_exactly_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for state in (
        KillSwitchState.WARNING,
        KillSwitchState.TRADING_DISABLED,
        KillSwitchState.EMERGENCY,
    ):
        runner = _Batches()
        with pytest.raises(script.Refused, match=f"kill_switch_not_active:{state.value}"):
            _run_apply(
                monkeypatch,
                args=_args(),
                kill=_KillSwitch(state),
                runner=runner,
                load_signer=_never_load_signer,
            )
        assert runner.calls == []


def test_apply_refuses_a_user_that_is_not_the_signer(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _Batches()
    rpc = FakeRpc()
    with pytest.raises(script.Refused, match="user_mismatch"):
        _run_apply(
            monkeypatch,
            args=_args("--user", OTHER),
            kill=_KillSwitch(KillSwitchState.ACTIVE),
            runner=runner,
            rpc=rpc,
        )
    assert runner.calls == [] and rpc.calls == []


def test_apply_runs_one_batch_by_default_and_prints_a_json_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = _Batches(_confirmed(8))
    rpc = FakeRpc(empty=10)
    code = _run_apply(
        monkeypatch,
        args=_args("--user", WALLET, "--reason", "R64 aluguel"),
        kill=_KillSwitch(KillSwitchState.ACTIVE),
        runner=runner,
        rpc=rpc,
    )
    assert code == 0
    assert rpc.calls == [WALLET, WALLET]  # listed for the signer's own key
    assert len(runner.calls) == 1
    call = runner.calls[0]
    assert len(call["batch"]) == 8
    assert call["reason"] == "R64 aluguel"
    assert call["actor"] == "everton"
    assert call["priority_fee_lamports"] == script.DEFAULT_PRIORITY_FEE_LAMPORTS
    assert isinstance(call["signer"], FakeSigner)
    out = capsys.readouterr().out
    line = next(ln for ln in out.splitlines() if ln.startswith("{"))
    assert json.loads(line)["status"] == "confirmed"
    assert json.loads(line)["n_closed"] == 8
    assert f"done: closed=8 lamports_recovered={8 * RENT - 15_000}" in out


def test_apply_runs_up_to_max_batches_and_stops_at_the_first_unconfirmed_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = _Batches(
        _confirmed(8),
        BatchResult("submitted", SIGNATURE, 0, 0, 8 * RENT, "confirm_pending"),
        _confirmed(4),
    )
    code = _run_apply(
        monkeypatch,
        args=_args("--max-batches", "3"),
        kill=_KillSwitch(KillSwitchState.ACTIVE),
        runner=runner,
        rpc=FakeRpc(empty=20),
    )
    assert code == script.EX_UNCONFIRMED
    assert len(runner.calls) == 2  # the third batch never ran
    lines = [json.loads(ln) for ln in capsys.readouterr().out.splitlines() if ln.startswith("{")]
    assert [ln["status"] for ln in lines] == ["confirmed", "submitted"]
    assert lines[1]["signature"] == SIGNATURE


def test_apply_re_reads_the_kill_switch_before_every_batch(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Astra (T4.77 review): EMERGENCY thrown while batch 0 confirms must stop
    batch 1 before it is signed — the switch is read once per batch, not once
    per run."""
    runner = _Batches(_confirmed(8), _confirmed(8), _confirmed(4))
    kill = _KillSwitch(KillSwitchState.ACTIVE, KillSwitchState.EMERGENCY)
    with pytest.raises(script.Refused, match="kill_switch_not_active:EMERGENCY"):
        _run_apply(
            monkeypatch,
            args=_args("--max-batches", "3"),
            kill=kill,
            runner=runner,
            rpc=FakeRpc(empty=20),
        )
    assert len(runner.calls) == 1
    assert kill.calls == 2
    lines = [json.loads(ln) for ln in capsys.readouterr().out.splitlines() if ln.startswith("{")]
    assert [ln["status"] for ln in lines] == ["confirmed"]


@pytest.mark.parametrize(
    ("result", "code"),
    [
        (BatchResult("refused", None, 0, 0, 8 * RENT, "simulation_lamports_short:1<2"), 65),
        (BatchResult("failed", SIGNATURE, 0, 0, 8 * RENT, "failed_on_chain"), 67),
    ],
)
def test_apply_exits_non_zero_when_a_batch_is_refused_or_failed(
    monkeypatch: pytest.MonkeyPatch, result: BatchResult, code: int
) -> None:
    runner = _Batches(result)
    assert (
        _run_apply(
            monkeypatch,
            args=_args(),
            kill=_KillSwitch(KillSwitchState.ACTIVE),
            runner=runner,
        )
        == code
    )


def test_apply_with_nothing_to_close_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = _Batches()
    code = _run_apply(
        monkeypatch,
        args=_args(),
        kill=_KillSwitch(KillSwitchState.ACTIVE),
        runner=runner,
        rpc=FakeRpc(empty=0, dust=2, token_2022=1),
    )
    assert code == 0 and runner.calls == []
    assert "nothing to close" in capsys.readouterr().out


def test_apply_refuses_an_unparsable_listing_before_any_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenRpc(FakeRpc):
        def call(self, method: str, params: list[Any]) -> Any:
            broken: dict[str, Any] = {"pubkey": "x", "account": {}}
            return {"context": {"slot": 1}, "value": [broken]}

    runner = _Batches()
    with pytest.raises(script.Refused, match="listing_unparsable"):
        _run_apply(
            monkeypatch,
            args=_args(),
            kill=_KillSwitch(KillSwitchState.ACTIVE),
            runner=runner,
            rpc=BrokenRpc(),
        )
    assert runner.calls == []


def test_main_maps_a_refusal_to_65(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def _refusing(args: Any) -> int:
        raise script.Refused("kill_switch_not_active:EMERGENCY")

    monkeypatch.setattr(script, "_apply", _refusing)
    assert script.main(["--apply"]) == script.EX_REFUSED
    assert "refused: kill_switch_not_active:EMERGENCY" in capsys.readouterr().err
