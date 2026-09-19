"""``meme_spot_swap.py`` (T4.73) -- the CLI itself: dry-run end to end against
the recorded fixture (network and RPC replaced by fakes), the guards reachable
with no database or signer at all (a token->token ``--apply``, the caps) and,
since T4.73b, the ``--apply`` logic itself (``apply_with``) against fakes for
the kill switch, the chain reader, the Jupiter client, the signer and the leg
runner -- never a real transaction, never a wallet key, in this suite. The
leg runner's own path (quote -> verify -> simulate -> sign -> send -> confirm)
is ``test_meme_spot_swap_send.py``.
"""

from __future__ import annotations

import asyncio
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
for extra in (SCRIPTS_DIR, SCRIPTS_DIR / "tests"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "packages/exchange-adapters/tests/fixtures/jupiter/quote_sol_to_wif_real.json"

import meme_spot_swap as script  # noqa: E402
from meme_spot_swap_send import LegResult  # noqa: E402
from test_meme_spot_swap_send import FakeSigner, wrap_tx_b64  # noqa: E402

from hunter_core.domain.enums import KillSwitchState  # noqa: E402
from hunter_exchanges.jupiter.models import JupiterQuote, JupiterSwapTransaction  # noqa: E402

WSOL = "So11111111111111111111111111111111111111112"
WIF = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


class FakeJupiterClient:
    def __init__(self) -> None:
        self.swap_calls = 0

    def __enter__(self) -> FakeJupiterClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def quote(
        self, *, input_mint: str, output_mint: str, amount: int, slippage_bps: int
    ) -> JupiterQuote:
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        return JupiterQuote.from_json(payload)

    def swap(self, *args: Any, **kwargs: Any) -> Any:
        self.swap_calls += 1
        raise AssertionError("dry-run without --user must never build a transaction")


def _fake_read_mint_decimals(rpc: object, mint: str) -> int:
    return 9 if mint == WSOL else 6


def _fake_rpc_client(*args: object, **kwargs: object) -> object:
    return object()


def _patch_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(script, "JupiterClient", FakeJupiterClient)
    monkeypatch.setattr(script, "read_mint_decimals", _fake_read_mint_decimals)
    monkeypatch.setattr(script, "SolanaTxRpcClient", _fake_rpc_client)


def _args(**overrides: Any) -> Any:
    base = script.parse_args(
        ["--from", "SOL", "--to", WIF, "--amount", "0.02", "--reason", "T4.73 teste"]
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_dry_run_prints_the_quote_and_never_touches_the_network_for_decimals(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_network(monkeypatch)
    code = script.main(["--from", "SOL", "--to", WIF, "--amount", "0.02", "--reason", "teste"])
    assert code == 0
    out = capsys.readouterr().out
    assert "quote So111" in out
    assert "in=0.02" in out
    assert "dry-run: nothing written" in out


def test_dry_run_reports_the_amount_cap_refusal_without_i_know(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_network(monkeypatch)
    code = script.main(
        ["--from", "SOL", "--to", WIF, "--amount", "0.06", "--reason", "teste"]  # > 0.05 soft cap
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "would refuse: amount_above_cap" in out


def test_dry_run_amount_above_soft_cap_passes_with_i_know(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_network(monkeypatch)
    code = script.main(
        ["--from", "SOL", "--to", WIF, "--amount", "0.06", "--reason", "teste", "--i-know"]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "would refuse" not in out


def test_dry_run_amount_above_hard_cap_is_refused_even_with_i_know(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """T4.73b, review finding 4: the "0.7 for 0.07" typo with ``--i-know``."""
    _patch_network(monkeypatch)
    code = script.main(
        ["--from", "SOL", "--to", WIF, "--amount", "0.7", "--reason", "teste", "--i-know"]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "would refuse: amount_above_hard_cap:0.7>0.10" in out


def test_apply_refuses_a_token_to_token_pair_before_touching_anything() -> None:
    args = _args(apply=True)
    args.from_, args.to = USDC, WIF
    with pytest.raises(script.Refused, match="apply_requires_a_sol_leg"):
        asyncio.run(script.run(args))


# --- T4.73b: ``apply_with`` (the ``--apply`` logic) against fakes, no engine/redis/key


class _Wallet:
    def __init__(self, lamports: int) -> None:
        self.lamports = lamports


class FakeChain:
    def __init__(self, lamports: int = 760_000_000) -> None:
        self.lamports = lamports
        self.rpc = object()

    def wallet(self, pubkey: str) -> _Wallet:
        return _Wallet(self.lamports)


class VerifyingFakeJupiterClient(FakeJupiterClient):
    """``.swap()`` answers a synthetic v0 tx for the wallet; an ``in_amount``
    override makes the real verifier refuse it."""

    def __init__(self, *, tx_in_amount: int = 20_000_000) -> None:
        super().__init__()
        self.tx_in_amount = tx_in_amount

    def swap(self, *args: Any, **kwargs: Any) -> Any:
        self.swap_calls += 1
        return JupiterSwapTransaction(
            swap_transaction_b64=wrap_tx_b64(in_amount=self.tx_in_amount),
            last_valid_block_height=None,
            prioritization_fee_lamports=None,
        )


class _KillSwitch:
    def __init__(self, *states: KillSwitchState) -> None:
        self.states = list(states)
        self.calls = 0

    async def __call__(self, conn: object, redis: object) -> KillSwitchState:
        self.calls += 1
        return self.states[min(self.calls - 1, len(self.states) - 1)]


class _Legs:
    def __init__(self, *results: LegResult) -> None:
        self.results = list(results)
        self.calls: list[dict[str, Any]] = []

    async def __call__(
        self, conn: object, chain: object, client: object, signer: object, **kw: Any
    ) -> LegResult:
        self.calls.append(kw)
        return self.results[len(self.calls) - 1]


def _apply_args(**overrides: Any) -> Any:
    args = _args(apply=True, round_trip=True)
    for key, value in overrides.items():
        setattr(args, key, value)
    return args


def _run_apply(
    monkeypatch: pytest.MonkeyPatch,
    *,
    args: Any,
    kill: _KillSwitch,
    legs: _Legs,
    chain: FakeChain | None = None,
    client: Any = None,
    env: dict[str, str] | None = None,
) -> int:
    monkeypatch.setattr(script, "read_effective_kill_switch_state", kill)
    monkeypatch.setattr(script, "run_apply_leg", legs)
    monkeypatch.setattr(script, "read_mint_decimals", _fake_read_mint_decimals)
    return asyncio.run(
        script.apply_with(
            args,
            conn=object(),
            redis=object(),
            chain=chain or FakeChain(),  # type: ignore[arg-type]
            client=client or VerifyingFakeJupiterClient(),
            load_signer=FakeSigner,  # type: ignore[arg-type]
            env=env if env is not None else {},
        )
    )


def test_apply_round_trip_sells_back_what_was_filled_with_the_impact_cap(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    kill = _KillSwitch(KillSwitchState.ACTIVE)
    legs = _Legs(
        LegResult("confirmed", 10_402_273, "sig1"), LegResult("confirmed", 19_900_000, "sig2")
    )
    code = _run_apply(monkeypatch, args=_apply_args(), kill=kill, legs=legs)
    assert code == 0
    assert len(legs.calls) == 2
    assert legs.calls[0]["input_mint"] == WSOL and legs.calls[0]["amount_atoms"] == 20_000_000
    assert legs.calls[1]["input_mint"] == WIF and legs.calls[1]["amount_atoms"] == 10_402_273
    assert legs.calls[1]["max_impact_pct"] == Decimal("1")  # finding 5
    assert kill.calls == 2  # finding 5: re-read after the hold
    out = capsys.readouterr().out
    assert "buy leg: confirmed filled=10402273 signature=sig1" in out
    assert "sell-back leg: confirmed filled=19900000 signature=sig2" in out


def test_apply_never_fires_the_sell_back_when_the_buy_is_only_submitted(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Finding 2: a buy that timed out in confirmation stops the round trip."""
    kill = _KillSwitch(KillSwitchState.ACTIVE)
    legs = _Legs(LegResult("submitted", 0, "sigX"))
    code = _run_apply(monkeypatch, args=_apply_args(), kill=kill, legs=legs)
    assert code == script.EX_UNCONFIRMED
    assert len(legs.calls) == 1
    assert "buy leg: submitted filled=0 signature=sigX" in capsys.readouterr().out


def test_apply_skips_the_sell_back_when_nothing_was_filled(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    kill = _KillSwitch(KillSwitchState.ACTIVE)
    legs = _Legs(LegResult("confirmed", 0, "sig1"))
    code = _run_apply(monkeypatch, args=_apply_args(), kill=kill, legs=legs)
    assert code == 0
    assert len(legs.calls) == 1
    assert "sell-back skipped" in capsys.readouterr().out


def test_apply_refuses_on_the_plan_verify_reason_before_a_second_swap_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 7: ``build_plan``'s verifier verdict is honoured; no leg runs."""
    kill = _KillSwitch(KillSwitchState.ACTIVE)
    legs = _Legs()
    client = VerifyingFakeJupiterClient(tx_in_amount=999)
    with pytest.raises(script.Refused, match="route_in_amount_mismatch|system_transfer"):
        _run_apply(monkeypatch, args=_apply_args(), kill=kill, legs=legs, client=client)
    assert client.swap_calls == 1
    assert legs.calls == []


def test_apply_refuses_when_the_wallet_would_drop_below_the_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 4: 0,32 - 0,02 - 0,01 = 0,29 < 0,30; ``--i-know`` does not help."""
    kill = _KillSwitch(KillSwitchState.ACTIVE)
    legs = _Legs()
    client = VerifyingFakeJupiterClient()
    with pytest.raises(script.Refused, match="wallet_below_floor_after_swap:0.29<0.30"):
        _run_apply(
            monkeypatch,
            args=_apply_args(i_know=True),
            kill=kill,
            legs=legs,
            chain=FakeChain(lamports=320_000_000),
            client=client,
        )
    assert client.swap_calls == 0 and legs.calls == []


def test_apply_reads_the_wallet_floor_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    kill = _KillSwitch(KillSwitchState.ACTIVE)
    legs = _Legs(LegResult("confirmed", 1, "s"))
    env = {"MEME_WALLET_MIN_SOL_AFTER_SWAP": "0.74"}  # 0.76 - 0.02 - 0.01 = 0.73 < 0.74
    with pytest.raises(script.Refused, match="wallet_below_floor_after_swap:0.73<0.74"):
        _run_apply(monkeypatch, args=_apply_args(round_trip=False), kill=kill, legs=legs, env=env)
    with pytest.raises(script.Refused, match="wallet_floor_invalid"):
        _run_apply(
            monkeypatch,
            args=_apply_args(round_trip=False),
            kill=kill,
            legs=legs,
            env={"MEME_WALLET_MIN_SOL_AFTER_SWAP": "abc"},
        )


def test_apply_refuses_a_hard_cap_amount_even_with_i_know(monkeypatch: pytest.MonkeyPatch) -> None:
    kill = _KillSwitch(KillSwitchState.ACTIVE)
    legs = _Legs()
    with pytest.raises(script.Refused, match="amount_above_hard_cap:0.7>0.10"):
        _run_apply(
            monkeypatch,
            args=_apply_args(amount="0.7", i_know=True),
            kill=kill,
            legs=legs,
            chain=FakeChain(lamports=5_000_000_000),
        )
    assert legs.calls == []


def test_apply_refuses_unless_the_kill_switch_is_exactly_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kill = _KillSwitch(KillSwitchState.WARNING)
    legs = _Legs()
    with pytest.raises(script.Refused, match="kill_switch_not_active:WARNING"):
        _run_apply(monkeypatch, args=_apply_args(), kill=kill, legs=legs)
    assert legs.calls == []


def test_apply_sell_back_is_an_exit_and_proceeds_after_the_switch_changed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Finding 5: the switch is re-read after ``--hold-s``; an exit is never
    blocked by an entry lock (doctrine), but the state is printed for the record."""
    kill = _KillSwitch(KillSwitchState.ACTIVE, KillSwitchState.TRADING_DISABLED)
    legs = _Legs(LegResult("confirmed", 5, "a"), LegResult("confirmed", 4, "b"))
    code = _run_apply(monkeypatch, args=_apply_args(), kill=kill, legs=legs)
    assert code == 0
    assert kill.calls == 2 and len(legs.calls) == 2
    assert "kill switch now TRADING_DISABLED" in capsys.readouterr().out


def test_apply_exits_non_zero_when_the_buy_leg_is_refused_or_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kill = _KillSwitch(KillSwitchState.ACTIVE)
    legs = _Legs(LegResult("refused", 0, None))
    assert _run_apply(monkeypatch, args=_apply_args(), kill=kill, legs=legs) == script.EX_REFUSED
    legs = _Legs(LegResult("failed", 0, "sigF"))
    assert _run_apply(monkeypatch, args=_apply_args(), kill=kill, legs=legs) == script.EX_FAILED
