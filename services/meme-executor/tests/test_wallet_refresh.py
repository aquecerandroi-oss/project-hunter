"""T4.51 — the wallet balance is re-read on its own cadence, not only when an
order happens.

Defect (17/09/2026): the last position closed at 09:29Z; the next order-time
read of ``state.wallet_lamports`` only happened when a live candidate was
handled, so ``hb:meme:executor`` kept publishing the balance from the moment
DOPEY was still open at 13:03Z while the chain (public RPC ``getBalance`` at
13:4xZ) already said 0.672509616 SOL and every position was closed.
``wallet_refresh_once`` is the fix: a bounded, timed-out read the kill-switch
tick (10 s) calls every time, whether or not any order happened."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from hunter_meme_executor.chain import WalletRead
from hunter_meme_executor.context import ExecutorContext, ExecutorState
from hunter_meme_executor.wallet_refresh import wallet_refresh_once

pytestmark = pytest.mark.unit

PUBKEY = "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1"


@dataclass
class FakeChain:
    lamports: int = 672_509_616
    down: bool = False
    delay_s: float = 0.0
    calls: list[str] = field(default_factory=lambda: list[str]())

    def wallet(self, pubkey: str) -> WalletRead:
        self.calls.append(pubkey)
        if self.delay_s:
            time.sleep(self.delay_s)
        if self.down:
            raise RuntimeError("rpc down")
        return WalletRead(pubkey, self.lamports, 1, datetime.now(UTC))


@dataclass
class FakeConfig:
    wallet_read_timeout_s: float = 1.5


@dataclass
class FakeSigner:
    pubkey: str = PUBKEY


@dataclass
class FakeContext:
    config: FakeConfig
    chain: FakeChain
    signer: FakeSigner | None
    state: ExecutorState = field(default_factory=ExecutorState)


def _ctx(*, no_signer: bool = False, **chain_kwargs: Any) -> FakeContext:
    signer = None if no_signer else FakeSigner()
    return FakeContext(FakeConfig(), FakeChain(**chain_kwargs), signer)


async def test_a_signerless_process_never_reads_the_chain() -> None:
    ctx = _ctx(no_signer=True)
    await wallet_refresh_once(cast(ExecutorContext, ctx))
    assert ctx.chain.calls == []
    assert ctx.state.wallet_lamports is None


async def test_a_good_read_publishes_the_fresh_balance() -> None:
    ctx = _ctx(lamports=672_509_616)
    await wallet_refresh_once(cast(ExecutorContext, ctx))
    assert ctx.state.wallet_lamports == 672_509_616
    assert ctx.state.wallet_read_at is not None
    assert ctx.chain.calls == [PUBKEY]
    assert ctx.state.rpc_errors == 0


async def test_a_failed_read_keeps_the_last_balance_and_counts_the_error() -> None:
    ctx = _ctx(lamports=645_172_518)
    await wallet_refresh_once(cast(ExecutorContext, ctx))
    stamp = ctx.state.wallet_read_at
    ctx.chain.down = True
    ctx.chain.lamports = 0  # if the failure path trusted this, equity would drop to zero
    await wallet_refresh_once(cast(ExecutorContext, ctx))
    assert ctx.state.wallet_lamports == 645_172_518, "a failed read must never lower equity"
    assert ctx.state.wallet_read_at == stamp, "the age of the number is the desk's own signal"
    assert ctx.state.rpc_errors == 1


async def test_a_read_past_the_deadline_is_a_failure_that_keeps_the_last_balance() -> None:
    ctx = _ctx(lamports=1_000_000_000, delay_s=0.2)
    ctx.config.wallet_read_timeout_s = 0.01
    await wallet_refresh_once(cast(ExecutorContext, ctx))
    assert ctx.state.wallet_lamports is None
    assert ctx.state.rpc_errors == 1
    # the thread is still sleeping; it must not touch state after the deadline
    await asyncio.sleep(0.3)
    assert ctx.state.wallet_lamports is None
