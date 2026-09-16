#!/usr/bin/env python3
"""Simulate a pump.fun buy/sell on mainnet through the executor's own code — never send.

Productionised from T4.8c's throwaway ``.claude/state/tmp/t48c_simulate*.py`` so the
owner can run it on the VPS. The path exercised is exactly the live one:

    ChainReader (curve + Global + blockhash)
      -> build.build_buy / build.build_sell
      -> BuiltTrade.verify        (docs/RISK_ENGINE_MEME.md §9.1)
      -> simulateTransaction      (sigVerify=false, the submitter's own framing)

**It cannot send.** No key is read (``--user`` is a *public* address; the script
never touches ``.env`` or the signer), the RPC client is built with
``allow_send=False`` and is additionally wrapped in :class:`SimulateOnlyRpc`,
whose ``send_transaction`` raises :class:`SimulateOnlyViolation`. A signature is
never produced: the 64 signature bytes are zeros.

Why it exists (T4.29c): T4.8c proved a *buy* on a holder-rewards curve
(``is_holder_reward = true``) and a *sell* only on normal curves — no HR sell was
ever simulated. ``docs/HOLDER_REWARDS_README.md`` (pump-public-docs commit
``81091419e4457566469d4e2a27f64ed84d42419c``, sha256 ``ce2a5788…``) states
"Trading holder rewards coins — There are **no changes to any trade instruction**",
and the ``sell`` of ``idl/pump.json`` at the same commit still declares the same
14 accounts. This script is how that claim gets proven on a real HR coin with a
real token balance instead of being taken on faith.

Usage (VPS, read-only, no wallet key needed — only the public address):

    uv run python infra/scripts/meme_simulate_trade.py --simulate-only --sell \\
        --mint <HR_MINT> --user ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4

    uv run python infra/scripts/meme_simulate_trade.py --simulate-only --buy \\
        --mint <MINT> --user <PUBKEY> --budget-sol 0.01

``--simulate-only`` is mandatory: without it the script exits 2 without one RPC
call. See ``docs/ACTIVATION.md`` §9b item 10 for what "ok" looks like.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]
for extra in ("services/meme-executor", "packages/exchange-adapters"):
    candidate = str(REPO_ROOT / extra)
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from hunter_exchanges.pumpfun.fee_config import (  # noqa: E402
    FEE_CONFIG_UNAVAILABLE_EVENT,
    FEE_PROGRAM_ID,
    decode_fee_config,
    fee_config_address,
)
from hunter_exchanges.pumpfun.tx_rpc import (  # noqa: E402
    MAINNET_PUBLIC_RPC_URL,
    SolanaTxRpcClient,
)
from hunter_meme_executor.build import build_buy, build_sell  # noqa: E402
from hunter_meme_executor.chain import ChainReader  # noqa: E402

DEFAULT_COMPUTE_UNIT_LIMIT = 150_000
DEFAULT_COMPUTE_UNIT_PRICE = 1
DEFAULT_SLIPPAGE_BPS = 500


class SimulateOnlyViolation(RuntimeError):
    """Raised if anything on the simulate path so much as reaches for a send."""


class RpcLike(Protocol):
    """The four read/simulate methods this script uses — no ``send_transaction`` in
    the shape at all, so a sending client cannot be passed in by accident."""

    @property
    def allow_send(self) -> bool: ...

    def call(self, method: str, params: list[Any]) -> Any: ...

    def get_account(self, address: str, *, commitment: str = ...) -> Any: ...

    def get_latest_blockhash(self, *, commitment: str = ...) -> tuple[str, int]: ...

    def simulate_transaction(
        self, transaction: bytes, *, sig_verify: bool = ..., replace_blockhash: bool = ...
    ) -> Any: ...


class SimulateOnlyRpc:
    """A delegating RPC wrapper with no way to send a transaction.

    Belt and braces: ``SolanaTxRpcClient`` already refuses ``sendTransaction``
    unless built with ``allow_send=True``. This wrapper makes the refusal a
    property of the *object this script holds*, so no later edit can hand the
    submitter a sending client by changing one keyword argument.
    """

    def __init__(self, inner: RpcLike, *, throttle_s: float = 1.1) -> None:
        if inner.allow_send:
            raise SimulateOnlyViolation("the inner RPC client was built with allow_send=True")
        self._inner = inner
        self._throttle_s = throttle_s
        self.calls: list[str] = []

    @property
    def allow_send(self) -> bool:
        return False

    def _record(self, method: str) -> None:
        if self.calls and self._throttle_s:
            time.sleep(self._throttle_s)  # the public RPC rate-limits; T4.8b/T4.8c hit 429
        self.calls.append(method)

    def call(self, method: str, params: list[Any]) -> Any:
        if method == "sendTransaction":
            raise SimulateOnlyViolation("sendTransaction is unreachable in simulate-only mode")
        self._record(method)
        return self._inner.call(method, params)

    def get_account(self, address: str, *, commitment: str = "confirmed") -> Any:
        self._record("getAccountInfo")
        return self._inner.get_account(address, commitment=commitment)

    def get_latest_blockhash(self, *, commitment: str = "confirmed") -> tuple[str, int]:
        self._record("getLatestBlockhash")
        return self._inner.get_latest_blockhash(commitment=commitment)

    def simulate_transaction(
        self, transaction: bytes, *, sig_verify: bool = False, replace_blockhash: bool = False
    ) -> Any:
        self._record("simulateTransaction")
        return self._inner.simulate_transaction(
            transaction, sig_verify=sig_verify, replace_blockhash=replace_blockhash
        )

    def send_transaction(self, *_args: Any, **_kwargs: Any) -> Any:
        raise SimulateOnlyViolation("send_transaction is unreachable in simulate-only mode")


def unsigned_transaction(message: bytes) -> bytes:
    """The framing the real submitter hands ``simulateTransaction``: one signature
    slot, zeroed (``hunter_core.execution.meme.submit._serialize``)."""
    return b"\x01" + b"\x00" * 64 + message


@dataclass(frozen=True, slots=True)
class SimulationArgs:
    mint: str
    user: str
    side: str
    budget_sol: Decimal = Decimal("0.01")
    token_amount: int | None = None
    max_slippage_bps: int = DEFAULT_SLIPPAGE_BPS
    compute_unit_limit: int = DEFAULT_COMPUTE_UNIT_LIMIT
    compute_unit_price_micro_lamports: int = DEFAULT_COMPUTE_UNIT_PRICE


def read_fee_config(rpc: SimulateOnlyRpc) -> dict[str, Any]:
    """The tiered fee schedule (T4.29c) — informational here: ``build.fee_bps`` still
    floors at the dated constant. Logs ``meme_fee_config_unavailable`` if unreadable."""
    address = fee_config_address()
    snapshot = rpc.get_account(address, commitment="confirmed")
    if snapshot is None or snapshot.owner != FEE_PROGRAM_ID:
        print(f"   {FEE_CONFIG_UNAVAILABLE_EVENT} address={address}")
        return {"event": FEE_CONFIG_UNAVAILABLE_EVENT, "address": address}
    config = decode_fee_config(snapshot.data_base64, owner=snapshot.owner)
    tiers = [
        {"threshold": t.market_cap_lamports_threshold, "fees": asdict(t.fees)}
        for t in config.fee_tiers
    ]
    print(f"   fee_config {address} slot={snapshot.slot} tiers={len(tiers)} {tiers[:2]}")
    return {"address": address, "slot": snapshot.slot, "fee_tiers": tiers}


def run_simulation(rpc: SimulateOnlyRpc, args: SimulationArgs) -> dict[str, Any]:
    """One buy or sell, built and simulated. Returns the record written to ``--json-out``."""
    if not isinstance(rpc, SimulateOnlyRpc):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise SimulateOnlyViolation("run_simulation refuses an RPC client it cannot vouch for")
    started = datetime.now(UTC)
    reader = ChainReader(rpc)  # pyright: ignore[reportArgumentType] - duck-typed on purpose
    fee_config = read_fee_config(rpc)
    global_account = reader.global_account()
    read = reader.curve(args.mint)
    if read is None:
        raise SystemExit(f"bonding curve not found for mint {args.mint}")
    account = read.account
    print(
        f"   curve slot={read.slot} complete={account.complete} "
        f"is_holder_reward={account.is_holder_reward} is_mayhem_mode={account.is_mayhem_mode} "
        f"layout={account.layout} creator={account.creator} token_program={read.token_program}"
    )
    blockhash, last_valid = reader.blockhash()
    print(f"   blockhash={blockhash} last_valid_block_height={last_valid}")

    if args.side == "buy":
        built = build_buy(
            read,
            global_account,
            user=args.user,
            budget_sol=args.budget_sol,
            max_slippage_bps=args.max_slippage_bps,
            blockhash=blockhash,
            last_valid_block_height=last_valid,
            compute_unit_limit=args.compute_unit_limit,
            compute_unit_price_micro_lamports=args.compute_unit_price_micro_lamports,
            creates_ata=not reader.token_account(args.user, args.mint, read.token_program).exists,
        )
    else:
        holding = reader.token_account(args.user, args.mint, read.token_program)
        amount = args.token_amount if args.token_amount is not None else holding.amount
        print(f"   token account exists={holding.exists} amount={holding.amount} selling={amount}")
        if amount <= 0:
            raise SystemExit(
                f"{args.user} holds no {args.mint}: a sell simulation needs a real balance"
            )
        built = build_sell(
            read,
            global_account,
            user=args.user,
            token_amount=amount,
            max_slippage_bps=args.max_slippage_bps,
            blockhash=blockhash,
            last_valid_block_height=last_valid,
            compute_unit_limit=args.compute_unit_limit,
            compute_unit_price_micro_lamports=args.compute_unit_price_micro_lamports,
        )
    verified = built.verify(built.message)
    print(f"   verify ok={verified is not None}")
    simulation = rpc.simulate_transaction(
        unsigned_transaction(built.message), sig_verify=False, replace_blockhash=True
    )
    print(
        f"== simulateTransaction {args.side.upper()} mint={args.mint} ok={simulation.ok} "
        f"err={simulation.err} units_consumed={simulation.units_consumed} slot={simulation.slot}"
    )
    for line in simulation.logs:
        if "Instruction:" in line or "Program log:" in line:
            print(f"      {line}")
    return {
        "task": "T4.29c",
        "started_at_utc": started.isoformat(),
        "side": args.side,
        "mint": args.mint,
        "user": args.user,
        "simulate_only": True,
        "send_transaction_calls": 0,
        "rpc_methods": list(rpc.calls),
        "fee_config": fee_config,
        "curve": {
            "slot": read.slot,
            "is_holder_reward": account.is_holder_reward,
            "is_mayhem_mode": account.is_mayhem_mode,
            "layout": account.layout,
            "complete": account.complete,
            "creator": account.creator,
        },
        "intent": built.intent_json(),
        "verified": verified is not None,
        "simulation": {
            "ok": simulation.ok,
            "err": simulation.err,
            "units_consumed": simulation.units_consumed,
            "slot": simulation.slot,
            "logs": list(simulation.logs),
        },
    }


def parse_args(argv: list[str]) -> tuple[SimulationArgs, argparse.Namespace]:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--simulate-only", action="store_true", help="mandatory; nothing is sent")
    side = parser.add_mutually_exclusive_group(required=True)
    side.add_argument("--buy", action="store_true")
    side.add_argument("--sell", action="store_true")
    parser.add_argument("--mint", required=True)
    parser.add_argument(
        "--user", required=True, help="PUBLIC address of the wallet; no key is read"
    )
    parser.add_argument("--budget-sol", default="0.01", help="buy only, SOL ceiling (default 0.01)")
    parser.add_argument("--amount", type=int, default=None, help="sell only, token subunits")
    parser.add_argument("--slippage-bps", type=int, default=DEFAULT_SLIPPAGE_BPS)
    parser.add_argument("--rpc", default=MAINNET_PUBLIC_RPC_URL)
    parser.add_argument("--json-out", default=None)
    parsed = parser.parse_args(argv)
    if not parsed.simulate_only:
        parser.error("--simulate-only is mandatory: this script never sends a transaction")
    return (
        SimulationArgs(
            mint=parsed.mint,
            user=parsed.user,
            side="buy" if parsed.buy else "sell",
            budget_sol=Decimal(str(parsed.budget_sol)),
            token_amount=parsed.amount,
            max_slippage_bps=parsed.slippage_bps,
        ),
        parsed,
    )


def main(argv: list[str] | None = None) -> int:
    args, parsed = parse_args(list(sys.argv[1:] if argv is None else argv))
    print(f"== meme_simulate_trade start {datetime.now(UTC).isoformat()} (UTC) rpc={parsed.rpc}")
    rpc = SimulateOnlyRpc(SolanaTxRpcClient(parsed.rpc))
    record = run_simulation(rpc, args)
    print(f"== rpc calls={len(rpc.calls)} sendTransaction=0 (unreachable in this mode)")
    if parsed.json_out:
        Path(parsed.json_out).write_text(json.dumps(record, indent=1), encoding="utf-8")
        print(f"   wrote {parsed.json_out}")
    return 0 if record["simulation"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
