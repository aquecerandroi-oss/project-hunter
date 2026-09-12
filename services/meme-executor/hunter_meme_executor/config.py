"""Boot of the executor: gates first, policy second, key last — every refusal named.

``docs/RISK_ENGINE_MEME.md`` §3.3/§3.4/§12, mechanised:

1. ``ENABLE_MEME_LIVE_TRADING`` off ⇒ paper mode: no gates file, no policy, no
   key required; nothing in the process may send (``allow_send=False``).
2. On ⇒ ``meme_gates.json`` must be valid (``hunter_core.execution.meme.gates``:
   A+B+C passed, or the written small-test authorization with C), **then** the
   five policy variables must all be present (``hunter_risk_meme.limits_from_env``),
   **then** an RPC URL of our own must be configured (§9.2: never the public
   endpoint for money), and only then the key is read — once, and scrubbed.
3. Any of those absent ⇒ :class:`MemeLiveTradingRefused` with the reason
   (``gates_file_missing``, ``policy_missing``, ``rpc_url_missing``,
   ``secret_key_missing``, …) and the process does not exist.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from hunter_core.domain.enums import KillSwitchState
from hunter_core.execution.meme.gates import MemeExecutionMode, MemeLiveTradingRefused, parse_flag
from hunter_core.execution.meme.signer import MemeSigner, boot_meme_execution
from hunter_exchanges.pumpfun.tx_rpc import MAINNET_PUBLIC_RPC_URL
from hunter_risk_meme import MEME_PAPER_V0, MemeLimits, MemePolicyMissing, limits_from_env

__all__ = ["INSTANCE", "ROLE", "ExecutorConfig", "boot"]

ROLE = "meme"
INSTANCE = "executor"
"""``hb:meme:executor`` — the brief's key. A fixed instance: one wallet, one
signer, one process (two would race the same signing locks by design)."""

Cluster = Literal["mainnet", "devnet"]


@dataclass(frozen=True, slots=True)
class ExecutorConfig:
    live: bool
    cluster: Cluster
    rpc_url: str
    limits: MemeLimits
    system_kill_switch: KillSwitchState
    kill_file: str | None
    auto_close_on_emergency: bool = False
    """§14.4 — default **false**: no state of the switch liquidates a position
    unless the owner says so in the environment."""
    approval_ttl_s: float = 30.0
    """An approval older than this is never executed (restart safety)."""
    loop_s: float = 1.0
    mark_s: float = 5.0
    kill_switch_poll_s: float = 10.0
    reconcile_s: float = 30.0
    confirm_timeout_s: float = 30.0
    compute_unit_limit: int = 400_000
    compute_unit_price_micro_lamports: int = 10_000
    small_test_max_trades: int | None = None

    @property
    def priority_fee_sol(self) -> Decimal:
        lamports = self.compute_unit_limit * self.compute_unit_price_micro_lamports // 1_000_000
        return Decimal(lamports) / Decimal(1_000_000_000)


def _float(env: Mapping[str, str], name: str, default: float) -> float:
    raw = (env.get(name) or "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = (env.get(name) or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _cluster(env: Mapping[str, str]) -> Cluster:
    raw = (env.get("MEME_EXECUTOR_CLUSTER") or "mainnet").strip().lower()
    if raw not in ("mainnet", "devnet"):
        raise MemeLiveTradingRefused("cluster_unknown", raw)
    return "devnet" if raw == "devnet" else "mainnet"


def _limits(env: Mapping[str, str], mode: MemeExecutionMode) -> MemeLimits:
    if not mode.live:
        try:
            return limits_from_env(env)
        except MemePolicyMissing:
            return MEME_PAPER_V0
    try:
        limits = limits_from_env(env)
    except MemePolicyMissing as exc:
        raise MemeLiveTradingRefused("policy_missing", str(exc)) from exc
    except ValueError as exc:
        raise MemeLiveTradingRefused("policy_invalid", str(exc)) from exc
    small = mode.gates.small_test if mode.gates is not None else None
    if small is not None:
        # The written authorization is a ceiling on top of the owner's policy.
        limits = MemeLimits.model_validate(
            {
                **limits.model_dump(),
                "profile": f"{limits.profile}+small_test",
                "max_sol_per_trade": min(limits.max_sol_per_trade, small.max_sol_per_trade),
                "max_exposure_per_mint_sol": min(
                    limits.max_exposure_per_mint_sol, small.max_sol_per_trade
                ),
                "wallet_max_sol": min(limits.wallet_max_sol, small.max_total_sol),
            }
        )
    return limits


def boot(
    env: MutableMapping[str, str], *, today: date, system_kill_switch: KillSwitchState
) -> tuple[ExecutorConfig, MemeExecutionMode, MemeSigner | None]:
    """Gates → policy → RPC → key. Live with anything missing never reaches the key."""
    mode = _mode_only(env, today=today)
    limits = _limits(env, mode)
    cluster = _cluster(env)
    rpc_url = (env.get("SOLANA_RPC_URL") or "").strip()
    if mode.live and not rpc_url:
        raise MemeLiveTradingRefused(
            "rpc_url_missing", "live execution needs SOLANA_RPC_URL (never the public endpoint)"
        )
    if mode.live and cluster == "mainnet" and "devnet" in rpc_url:
        raise MemeLiveTradingRefused("rpc_url_cluster_mismatch", "devnet URL with cluster=mainnet")
    mode, signer = boot_meme_execution(env, today=today)
    kill_file = (env.get("MEME_KILL_FILE") or "").strip() or None
    config = ExecutorConfig(
        live=mode.live,
        cluster=cluster,
        rpc_url=rpc_url or MAINNET_PUBLIC_RPC_URL,
        limits=limits,
        system_kill_switch=system_kill_switch,
        kill_file=kill_file,
        auto_close_on_emergency=parse_flag(env.get("MEME_AUTO_CLOSE_ON_EMERGENCY")),
        approval_ttl_s=_float(env, "MEME_LIVE_APPROVAL_TTL_S", 30.0),
        loop_s=_float(env, "MEME_LIVE_LOOP_S", 1.0),
        mark_s=_float(env, "MEME_LIVE_MARK_S", 5.0),
        confirm_timeout_s=_float(env, "MEME_LIVE_CONFIRM_TIMEOUT_S", 30.0),
        compute_unit_limit=_int(env, "MEME_COMPUTE_UNIT_LIMIT", 400_000),
        compute_unit_price_micro_lamports=_int(
            env, "MEME_COMPUTE_UNIT_PRICE_MICRO_LAMPORTS", 10_000
        ),
        small_test_max_trades=(
            mode.gates.small_test.max_trades
            if mode.gates is not None and mode.gates.small_test is not None
            else None
        ),
    )
    return config, mode, signer


def _mode_only(env: Mapping[str, str], *, today: date) -> MemeExecutionMode:
    """The gates decision without touching the key (``boot_meme_execution`` reads it)."""
    from hunter_core.execution.meme.gates import load_execution_mode

    return load_execution_mode(env, today=today)


def process_environment() -> MutableMapping[str, str]:
    """The real environment — passed explicitly so tests never touch ``os.environ``."""
    return os.environ
