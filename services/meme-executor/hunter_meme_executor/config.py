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
4. ``MEME_LIVE_AUTO_APPROVE`` (T4.28, stage 1) is read only after 1–2 and only
   with a written small test in the gates: on without one ⇒
   ``auto_approve_needs_small_test``, before the key; on without the live flag
   ⇒ ignored (an inert executor opens nothing).
"""

from __future__ import annotations

import os
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from hunter_core.domain.enums import KillSwitchState
from hunter_core.execution.meme.gates import (
    ENV_GATES_FILE,
    MemeExecutionMode,
    MemeGates,
    MemeLiveTradingRefused,
    SmallTestAuthorization,
    parse_flag,
)
from hunter_core.execution.meme.signer import MemeSigner, boot_meme_execution
from hunter_exchanges.jupiter.client import DEFAULT_JUPITER_BASE_URL
from hunter_exchanges.pumpfun.tx_rpc import MAINNET_PUBLIC_RPC_URL
from hunter_meme_executor.config_env import (
    Cluster,
    bps,
    cluster,
    float_env,
    int_env,
    positive_decimal,
    tolerance,
)
from hunter_meme_executor.conviction import ConvictionConfig
from hunter_meme_executor.send_tuning import SendTuning
from hunter_risk_meme import MEME_PAPER_V0, MemeLimits, MemePolicyMissing, limits_from_env

__all__ = [
    "ENV_AUTO_APPROVE",
    "INSTANCE",
    "ROLE",
    "ExecutorConfig",
    "boot",
    "effective_limits",
    "with_gates",
]

ROLE = "meme"
INSTANCE = "executor"
ENV_AUTO_APPROVE = "MEME_LIVE_AUTO_APPROVE"
"""``hb:meme:executor`` — the brief's key. A fixed instance: one wallet, one
signer, one process (two would race the same signing locks by design)."""


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
    small_test_max_total_sol: Decimal | None = None
    auto_approve: bool = False
    """T4.28 stage 1 — ``MEME_LIVE_AUTO_APPROVE``: the executor opens the desk's
    ``operator`` proposal as live without the click. Read only with the live flag
    on **and** a written small test in the gates (``auto_approve_needs_small_test``
    otherwise); inert without the live flag."""
    auto_approve_max_per_hour: int = 5
    auto_approve_refusal_cooldown_s: float = 120.0
    """T4.28f — ``MEME_LIVE_AUTO_APPROVE_REFUSAL_COOLDOWN_S``: how long a mint the
    admission refused for a reason that needs more than a tick to change
    (``auto_approve.DETERMINISTIC_REFUSALS``) is not re-opened by the robot. ``0``
    disables the skip (and the query with it)."""
    risk_read_timeout_s: float = 1.5
    """T4.45 - ``MEME_RISK_READ_TIMEOUT_S``: the hard deadline of the executor's
    own ``/in-memory-coin`` read on the admission path. Past it the read is a
    failure and the admission refuses by name, never waits."""
    wallet_read_timeout_s: float = 1.5
    """T4.51 - ``MEME_WALLET_REFRESH_TIMEOUT_S``: the hard deadline of the
    kill-switch tick's own ``getBalance`` read (``wallet_refresh.py``). Past it
    the read is a failure — the last known balance is kept, never zeroed."""
    creator_sell_tolerance_pct: Decimal = Decimal("0.02")
    """T4.45 - ``MEME_CREATOR_SELL_TOLERANCE_PCT``: how much of his recorded
    allocation a creator may be missing before the chain read calls it a sale."""
    gates_file: str | None = None
    """T4.28d — the path the gates were read from, so the runtime can re-read it
    on an mtime change (``gates_reload``). ``None`` while the live flag is off."""
    env_limits: MemeLimits | None = None
    """The owner's policy **before** the written scope's ceiling. A reload
    recomposes from this, never from ``limits``: ``min`` over an
    already-tightened value would pin yesterday's smaller number forever."""
    treasury_enabled: bool = False
    """T4.54 — ``MEME_TREASURY_ENABLED``: Everton's flag, off by default. On, the
    tick may swap USDC -> SOL below ``treasury_sol_floor``; needs ``live`` too."""
    treasury_sol_floor: Decimal = Decimal("0.30")
    """``MEME_TREASURY_SOL_FLOOR`` — below this the wallet is topped up."""
    treasury_sol_target: Decimal = Decimal("0.60")
    """``MEME_TREASURY_SOL_TARGET`` — sized to, never overshot; refused by name
    above ``wallet_max_sol - max_sol_per_trade`` (T4.54b fix E)."""
    treasury_max_usdc_per_swap: Decimal = Decimal("25")
    """``MEME_TREASURY_MAX_USDC_PER_SWAP`` — the ceiling of one attempt."""
    treasury_max_usdc_per_day: Decimal = Decimal("50")
    """``MEME_TREASURY_MAX_USDC_PER_DAY`` — every confirmed *or submitted* swap, 24 h."""
    treasury_max_slippage_bps: int = 50
    """``MEME_TREASURY_MAX_SLIPPAGE_BPS`` — sent to the quote, required back
    unchanged, and decoded from the built ``route`` (``treasury_verify``)."""
    treasury_jupiter_base_url: str = DEFAULT_JUPITER_BASE_URL
    """``MEME_TREASURY_JUPITER_BASE_URL`` — keyless ``lite-api.jup.ag/swap/v1``
    by default (``quote-api.jup.ag/v6`` is gone); keyed: ``api.jup.ag/swap/v1``."""
    treasury_min_interval_s: float = 600.0
    """``MEME_TREASURY_MIN_INTERVAL_S`` — no two attempts (successful, failed or
    refused) closer than this; a persistent refusal must not hammer every tick."""
    send: SendTuning = SendTuning()
    """T4.55 — priority-fee floor/cap, exit and panic slippage, re-send cadence
    (``send_tuning.py``). ``compute_unit_price_micro_lamports`` above is only the
    static fallback of a context without a fee reader."""
    conviction: ConvictionConfig = ConvictionConfig()
    """T4.61b — ``MEME_CONVICTION_SIZING`` (default off) and the ladder's numbers
    (``conviction.py``): the buy as a fraction of the cap, never above it."""

    @property
    def base_limits(self) -> MemeLimits:
        """What ``effective_limits`` composes on top of (``limits`` for a config
        built before T4.28d, which has no written scope folded in)."""
        return self.env_limits or self.limits

    @property
    def priority_fee_sol(self) -> Decimal:
        lamports = self.compute_unit_limit * self.compute_unit_price_micro_lamports // 1_000_000
        return Decimal(lamports) / Decimal(1_000_000_000)


def effective_limits(base: MemeLimits, small: SmallTestAuthorization | None) -> MemeLimits:
    """The owner's policy with the written scope's ceiling folded in — **one**
    place for this arithmetic, used by the boot and by the runtime reload (T4.28d).

    ``base`` is always the environment's policy, never an already-composed one: a
    scope the owner widens (0,25 → 0,72 on 16/09/2026) must widen the effective
    policy too, and ``min`` over the previous composition never would.
    """
    if small is None:
        return base
    return MemeLimits.model_validate(
        {
            **base.model_dump(),
            "profile": f"{base.profile}+small_test",
            "max_sol_per_trade": min(base.max_sol_per_trade, small.max_sol_per_trade),
            "max_exposure_per_mint_sol": min(
                base.max_exposure_per_mint_sol, small.max_sol_per_trade
            ),
            "wallet_max_sol": min(base.wallet_max_sol, small.max_total_sol),
        }
    )


def with_gates(config: ExecutorConfig, gates: MemeGates) -> ExecutorConfig:
    """The same config against a freshly read gates file: the effective policy and
    the scope's two published numbers, recomposed. Counters live in the ledger and
    are not touched here."""
    small = gates.small_test
    return replace(
        config,
        limits=effective_limits(config.base_limits, small),
        small_test_max_trades=None if small is None else small.max_trades,
        small_test_max_total_sol=None if small is None else small.max_total_sol,
    )


def _base_limits(env: Mapping[str, str], mode: MemeExecutionMode) -> MemeLimits:
    """The five ``MEME_*`` numbers, before any written ceiling."""
    if not mode.live:
        try:
            return limits_from_env(env)
        except MemePolicyMissing:
            return MEME_PAPER_V0
    try:
        return limits_from_env(env)
    except MemePolicyMissing as exc:
        raise MemeLiveTradingRefused("policy_missing", str(exc)) from exc
    except ValueError as exc:
        raise MemeLiveTradingRefused("policy_invalid", str(exc)) from exc


def boot(
    env: MutableMapping[str, str], *, today: date, system_kill_switch: KillSwitchState
) -> tuple[ExecutorConfig, MemeExecutionMode, MemeSigner | None]:
    """Gates → policy → RPC → key. Live with anything missing never reaches the key."""
    mode = _mode_only(env, today=today)
    env_limits = _base_limits(env, mode)
    small_at_boot = mode.gates.small_test if mode.gates is not None else None
    limits = effective_limits(env_limits, small_at_boot)
    cluster_name = cluster(env)
    rpc_url = (env.get("SOLANA_RPC_URL") or "").strip()
    if mode.live and not rpc_url:
        raise MemeLiveTradingRefused(
            "rpc_url_missing", "live execution needs SOLANA_RPC_URL (never the public endpoint)"
        )
    if mode.live and cluster_name == "mainnet" and "devnet" in rpc_url:
        raise MemeLiveTradingRefused("rpc_url_cluster_mismatch", "devnet URL with cluster=mainnet")
    small = mode.gates.small_test if mode.gates is not None else None
    auto_approve = parse_flag(env.get(ENV_AUTO_APPROVE)) and mode.live
    if auto_approve and small is None:
        # Stage 1 exists only inside a scope the owner wrote; without one the flag
        # is a contradiction, refused before the key is read.
        raise MemeLiveTradingRefused(
            "auto_approve_needs_small_test",
            f"{ENV_AUTO_APPROVE} is on but meme_gates.json has no small_test_authorization",
        )
    mode, signer = boot_meme_execution(env, today=today)
    kill_file = (env.get("MEME_KILL_FILE") or "").strip() or None
    config = ExecutorConfig(
        live=mode.live,
        cluster=cluster_name,
        rpc_url=rpc_url or MAINNET_PUBLIC_RPC_URL,
        limits=limits,
        system_kill_switch=system_kill_switch,
        kill_file=kill_file,
        auto_close_on_emergency=parse_flag(env.get("MEME_AUTO_CLOSE_ON_EMERGENCY")),
        approval_ttl_s=float_env(env, "MEME_LIVE_APPROVAL_TTL_S", 30.0),
        loop_s=float_env(env, "MEME_LIVE_LOOP_S", 1.0),
        mark_s=float_env(env, "MEME_LIVE_MARK_S", 5.0),
        confirm_timeout_s=float_env(env, "MEME_LIVE_CONFIRM_TIMEOUT_S", 30.0),
        compute_unit_limit=int_env(env, "MEME_COMPUTE_UNIT_LIMIT", 400_000),
        compute_unit_price_micro_lamports=int_env(
            env, "MEME_COMPUTE_UNIT_PRICE_MICRO_LAMPORTS", 10_000
        ),
        small_test_max_trades=None if small is None else small.max_trades,
        small_test_max_total_sol=None if small is None else small.max_total_sol,
        auto_approve=auto_approve,
        auto_approve_max_per_hour=max(0, int_env(env, "MEME_LIVE_AUTO_APPROVE_MAX_PER_HOUR", 5)),
        auto_approve_refusal_cooldown_s=max(
            0.0, float_env(env, "MEME_LIVE_AUTO_APPROVE_REFUSAL_COOLDOWN_S", 120.0)
        ),
        risk_read_timeout_s=max(0.1, float_env(env, "MEME_RISK_READ_TIMEOUT_S", 1.5)),
        wallet_read_timeout_s=max(0.1, float_env(env, "MEME_WALLET_REFRESH_TIMEOUT_S", 1.5)),
        creator_sell_tolerance_pct=tolerance(env),
        gates_file=(env.get(ENV_GATES_FILE) or "").strip() or None if mode.live else None,
        env_limits=env_limits,
        treasury_enabled=parse_flag(env.get("MEME_TREASURY_ENABLED")),
        treasury_sol_floor=positive_decimal(env, "MEME_TREASURY_SOL_FLOOR", Decimal("0.30")),
        treasury_sol_target=positive_decimal(env, "MEME_TREASURY_SOL_TARGET", Decimal("0.60")),
        treasury_max_usdc_per_swap=positive_decimal(
            env, "MEME_TREASURY_MAX_USDC_PER_SWAP", Decimal("25")
        ),
        treasury_max_usdc_per_day=positive_decimal(
            env, "MEME_TREASURY_MAX_USDC_PER_DAY", Decimal("50")
        ),
        treasury_max_slippage_bps=bps(env, "MEME_TREASURY_MAX_SLIPPAGE_BPS", 50),
        treasury_min_interval_s=max(0.0, float_env(env, "MEME_TREASURY_MIN_INTERVAL_S", 600.0)),
        treasury_jupiter_base_url=(env.get("MEME_TREASURY_JUPITER_BASE_URL") or "").strip()
        or DEFAULT_JUPITER_BASE_URL,
        send=SendTuning.from_env(env),
        conviction=ConvictionConfig.from_env(env),
    )
    return config, mode, signer


def _mode_only(env: Mapping[str, str], *, today: date) -> MemeExecutionMode:
    """The gates decision without touching the key (``boot_meme_execution`` reads it)."""
    from hunter_core.execution.meme.gates import load_execution_mode

    return load_execution_mode(env, today=today)


def process_environment() -> MutableMapping[str, str]:
    """The real environment — passed explicitly so tests never touch ``os.environ``."""
    return os.environ
