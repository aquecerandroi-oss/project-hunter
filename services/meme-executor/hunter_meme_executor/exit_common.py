"""Shared between ``exits.py`` (bonding curve), ``pumpswap_exit.py`` (T4.29a)
and ``event_exits.py`` (T4.63) — kept in its own module so none imports the
other.

T4.63 moved three things here so the tick and the event path decide with the
**same** arithmetic and never both send: ``exit_params`` (the rule-set's
numbers → ``ExitParams``), ``mark_sol`` (what a full sell nets now, from the
reserves of a curve read *or* of a WS notification — the same ``quote_sell``)
and ``exit_lock`` (one ``asyncio.Lock`` per position; whoever holds it re-reads
the row before selling, so a position the other path just closed is nothing).
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any

from hunter_core.db.session import role_session
from hunter_core.execution.meme.gates import parse_flag
from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.quote import CurveReserves, quote_sell
from hunter_meme_executor.build import fee_bps
from hunter_meme_executor.context import ExecutorContext
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.repo import OpenPosition, latest_sell_order, set_exit_intent
from hunter_meme_executor.send_tuning import SendTuning
from hunter_risk_meme import EXIT_REASONS, ExitParams, MemeLimits

__all__ = [
    "BACKOFF_S",
    "ENV_CLOSE_ATA_ON_FULL_SELL",
    "ENV_EXIT_PANIC_FROM_ATTEMPT",
    "ENV_EXIT_RETRY_MAX_ATTEMPTS",
    "LAMPORTS",
    "RETRY_EXHAUSTED",
    "close_ata_on_full_sell",
    "exit_lock",
    "exit_params",
    "exit_retry_exhausted",
    "is_launch_position",
    "mark_blocked",
    "mark_sol",
    "pending_sell_retry",
    "retry_reason",
    "sell_slippage_bps",
]

logger = get_logger(__name__)
BACKOFF_S = (2, 4, 8, 16, 32, 60)
ENV_CLOSE_ATA_ON_FULL_SELL = "MEME_CLOSE_ATA_ON_FULL_SELL"
ENV_EXIT_PANIC_FROM_ATTEMPT = "MEME_EXIT_PANIC_FROM_ATTEMPT"
ENV_EXIT_RETRY_MAX_ATTEMPTS = "MEME_EXIT_RETRY_MAX_ATTEMPTS"
DEFAULT_PANIC_FROM_ATTEMPT = 0
"""T4.88 — ``0`` = a escada de hoje (tolerância só por motivo). A medição das 101
vendas reais (17→23/09) não estabelece retorno esperado para escalar: dois casos
de retentativa, +0,0031 SOL num (GAMON) e −0,0001 no outro, e o de GAMON é o
mesmo caso que a intenção pendente já resolve. Ligar é decisão de política do
dono (``1`` = pânico já na 1.ª tentativa, ``2`` = a partir da retentativa)."""
DEFAULT_RETRY_MAX_ATTEMPTS = len(BACKOFF_S)
RETRY_EXHAUSTED = "exit_retry_exhausted"
LAMPORTS = Decimal(1_000_000_000)


def close_ata_on_full_sell(env: Mapping[str, str]) -> bool:
    """T4.46 — OFF by default: a full sell closes the mint's ATA (rent back,
    R43) only when Everton sets ``MEME_CLOSE_ATA_ON_FULL_SELL=1`` in the VPS
    ``.env``. Review of 5bbae3ab: safe, but a systematic close error would park
    every position at simulation, and the first mainnet close is the only
    real test — a change to the real sell transaction is his flag."""
    return parse_flag(env.get(ENV_CLOSE_ATA_ON_FULL_SELL), default=False)


def exit_params(params: Mapping[str, Any], lim: MemeLimits) -> ExitParams:
    """The rule-set's ``target_x``/``trailing_pct``/``max_hold_s`` as the
    position carries them, the profile's numbers for whatever is missing.
    T4.67b: the launch set's own names win when present —
    ``max_drawdown_from_peak_pct`` (per cent, the trailing rule) and
    ``time_stop_s`` (**seconds**; ``max_hold_s`` always was seconds too)."""
    drawdown = params.get("max_drawdown_from_peak_pct")
    raw_trailing = params.get("trailing_pct", lim.trailing_from_peak_pct * 100)
    trailing = Decimal(str(raw_trailing if drawdown is None else drawdown)) / 100
    hold = params.get("time_stop_s")
    if hold is None:
        hold = params.get("max_hold_s", lim.time_stop_s)
    return ExitParams(
        target_multiple=Decimal(str(params.get("target_x", lim.target_multiple))),
        trailing_from_peak_pct=trailing if 0 < trailing < 1 else lim.trailing_from_peak_pct,
        time_stop_s=max(1, int(hold)),
    )


def is_launch_position(params: Mapping[str, Any]) -> bool:
    """T4.67b: a position the launch profile opened (``params.lane = launch``)."""
    return params.get("lane") == "launch"


def mark_sol(ctx: ExecutorContext, reserves: CurveReserves, tokens: int) -> Decimal | None:
    """Net SOL of selling everything now (fees and the network fee out), or
    ``None`` when the curve no longer trades. ``Decimal(0)`` when the proceeds
    do not even cover the fees — a number, because the curve *is* readable."""
    if reserves.complete or tokens <= 0:
        return None
    try:
        quote = quote_sell(
            reserves,
            tokens,
            fee_bps(ctx.chain.global_account()),
            max_slippage_bps=int(ctx.config.limits.max_slippage_pct * 10_000),
        )
    except ValueError:
        return Decimal(0)
    net = Decimal(quote.net_proceeds) / LAMPORTS - ctx.config.limits.network_fee_sol
    return max(Decimal(0), net)


def _int_env(env: Mapping[str, str], name: str, default: int) -> int:
    """Tuning, never authorization (T4.28h): um valor ilegível cai no padrão."""
    raw = (env.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= 0 else default


def sell_slippage_bps(
    send: SendTuning, reason: str, *, attempt: int, env: Mapping[str, str]
) -> int:
    """A tolerância com que a tentativa ``attempt`` desta saída é montada.

    Base: a de hoje, por motivo (``creator_dump``/``rug_signal`` = pânico, o
    resto 5 %). Com ``MEME_EXIT_PANIC_FROM_ATTEMPT = n > 0``, a tentativa ``n``
    em diante usa **exatamente** a tolerância de pânico, o teto configurado
    (``MEME_PANIC_EXIT_MAX_SLIPPAGE_PCT``, já limitado a 50 % pela cota) — nem
    se a normal estiver configurada acima dela. Só na curva: a PumpSwap segue
    por motivo (``pumpswap_exit.py``, fora da T4.88). Atenção (Astra, T4.88):
    15 % é tolerância **contra a cotação de cada tentativa**, não um limite de
    perda desde a entrada — recotar em série admite perdas acumuladas maiores."""
    start = _int_env(env, ENV_EXIT_PANIC_FROM_ATTEMPT, DEFAULT_PANIC_FROM_ATTEMPT)
    if start <= 0 or attempt < start:
        return send.exit_slippage_bps(reason)
    return int(send.panic_exit_max_slippage_pct * 100)


def retry_reason(
    intent: Mapping[str, Any] | None, now: datetime, *, env: Mapping[str, str]
) -> str | None:
    """O motivo que uma saída já decidida ainda deve à posição, ou ``None``.

    Lê **a intenção durável** da linha: o motivo original (nunca um inventado),
    o ``next_attempt_at`` que a falha escreveu (ausente = devida agora, que é o
    caso da falha descoberta pelo laço de reconciliação de 30 s) e o teto de
    tentativas automáticas. Quem diz que a tentativa falhou é a linha da ordem,
    não isto (``pending_sell_retry``). Uma intenção ``blocked`` é uma recusa
    nomeada: o bloqueio manda, não esta retentativa."""
    if not intent or intent.get("blocked") or exit_retry_exhausted(intent, env=env):
        return None
    if _int_env(env, ENV_EXIT_RETRY_MAX_ATTEMPTS, DEFAULT_RETRY_MAX_ATTEMPTS) <= 0:
        return None  # ``0`` desliga a retentativa automática por completo
    reason = intent.get("reason")
    if not isinstance(reason, str) or reason not in EXIT_REASONS:
        return None
    raw = intent.get("next_attempt_at")
    if raw is None:
        return reason
    try:
        due = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    return reason if due <= now else None


def exit_retry_exhausted(intent: Mapping[str, Any] | None, *, env: Mapping[str, str]) -> bool:
    """A saída decidida já gastou o teto de retentativas **automáticas**
    (``MEME_EXIT_RETRY_MAX_ATTEMPTS``, padrão ``6`` = o comprimento do backoff;
    ``0`` desliga a retentativa e nunca esgota nada). O teto limita só o reenvio
    sem gatilho novo: uma regra que dispare continua vendendo — bloqueado
    significa **ainda exposto**, nunca saída concluída."""
    cap = _int_env(env, ENV_EXIT_RETRY_MAX_ATTEMPTS, DEFAULT_RETRY_MAX_ATTEMPTS)
    if not intent or cap <= 0:
        return False
    try:
        attempt = int(intent.get("attempt", 0) or 0)
    except (TypeError, ValueError):
        return False
    return attempt >= cap


async def pending_sell_retry(
    ctx: ExecutorContext, position: OpenPosition, *, now: datetime
) -> str | None:
    """T4.88 — "a tentativa acaba, a intenção não" (``docs/RISK_ENGINE_MEME.md``).

    ``decide_exit`` é sem memória: depois de uma venda que falhou, se o preço cai
    na banda morta (abaixo do alvo, acima do trailing) nenhuma regra dispara e o
    ``next_attempt_at`` que a falha escreveu fica sem leitor — a posição continua
    aberta com a saída já decidida. Aconteceu em GAMON (21/09): 17,4 s até a
    tentativa 2, −0,0079 SOL de marca no caminho. O gatilho é o **estado durável
    da ordem** (``failed``), não a intenção, porque a reconciliação de 30 s
    descobre falhas sem tocar na intenção."""
    intent = position.exit_intent
    if not intent:
        return None
    if intent.get("blocked") == RETRY_EXHAUSTED:
        # Durável na linha; o mapa em memória nasce vazio num restart — o
        # heartbeat volta a mostrá-lo sem regravar nem recontar (Astra, T4.88).
        ctx.state.blocked_exits.setdefault(position.id, RETRY_EXHAUSTED)
        return None
    exhausted = exit_retry_exhausted(intent, env=os.environ)
    reason = None if exhausted else retry_reason(intent, now, env=os.environ)
    if not exhausted and reason is None:
        return None  # nada devido agora: nenhuma leitura do banco
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        latest = await latest_sell_order(session, position.proposal_id)
    if latest is None or latest.status != "failed":
        return None
    if exhausted:
        await mark_blocked(ctx, position, str(intent.get("reason", "")), RETRY_EXHAUSTED, now)
        return None
    return reason


def exit_lock(ctx: ExecutorContext, position_id: str) -> asyncio.Lock:
    """T4.63: the tick (``exits.manage_position``) and the event path
    (``exits.sell_on_event``) serialize on this — and re-read the row once
    inside, so the second one in finds the position closed and sends nothing."""
    return ctx.state.exit_locks.setdefault(position_id, asyncio.Lock())


async def mark_blocked(
    ctx: ExecutorContext, position: OpenPosition, reason: str, block: str, now: datetime
) -> None:
    """Record a named, non-silent exit refusal — never a quiet skip."""
    intent: dict[str, Any] = {"reason": reason, "decided_at": now.isoformat(), "blocked": block}
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        await set_exit_intent(session, position.id, intent, now=now)
    ctx.state.blocked_exits[position.id] = block
    ctx.state.exits_blocked += 1
    logger.warning(
        "meme_live_exit_blocked",
        position_id=position.id,
        mint=position.mint,
        reason=reason,
        blocked=block,
    )
