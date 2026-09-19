"""``meme_spot_swap.py`` (T4.73) -- the CLI itself: dry-run end to end against
the recorded fixture (network and RPC replaced by fakes) and the two guards
reachable with no database or signer at all: a token->token ``--apply`` and
an amount over the cap. The kill-switch/simulate/sign/send path needs a real
Postgres, Redis and RPC and is exercised only through the pure primitives it
is built from (``meme_spot_swap_rules``/``meme_spot_swap_send`` share
``hunter_meme_executor.treasury_rules``/``spot_verify``, both covered
elsewhere) -- never a real transaction, never a wallet key, in this suite.
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
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "packages/exchange-adapters/tests/fixtures/jupiter/quote_sol_to_wif_real.json"

import meme_spot_swap as script  # noqa: E402

from hunter_exchanges.jupiter.models import JupiterQuote  # noqa: E402

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
        ["--from", "SOL", "--to", WIF, "--amount", "1", "--reason", "teste"]  # 1 SOL >> 0.05 cap
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "would refuse: amount_above_cap" in out


def test_dry_run_amount_above_cap_passes_with_i_know(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_network(monkeypatch)
    code = script.main(
        ["--from", "SOL", "--to", WIF, "--amount", "1", "--reason", "teste", "--i-know"]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "would refuse" not in out


def test_apply_refuses_a_token_to_token_pair_before_touching_anything() -> None:
    args = _args(apply=True)
    args.from_, args.to = USDC, WIF
    with pytest.raises(script.Refused, match="apply_requires_a_sol_leg"):
        asyncio.run(script.run(args))
