"""T4.88 contra um Postgres real (testcontainers; mesma bancada de
``test_live_persistence.py``): **a venda que falhou continua devida**.

Regressão de GAMON (21/09/2026). A tentativa 1 morreu com ``6003
TooLittleSolReceived``; o preço caiu para a banda morta — abaixo do alvo e ainda
acima do trailing — e ``decide_exit``, que é sem memória, deixou de pedir a
saída. O ``next_attempt_at`` que a falha tinha escrito ficou sem leitor: a
tentativa 2 só saiu 17,4 s depois, quando o trailing finalmente armou, e a marca
já tinha caído de 0,0803 para 0,0724 (−0,0079 SOL medidos na fita). Aqui o tick
seguinte reenvia sozinho, com o motivo original, uma chave de ordem nova e a
tolerância de hoje.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
from sqlalchemy import text

from hunter_core.execution.meme.base58 import b58encode
from hunter_meme_executor.entries import entries_once
from hunter_meme_executor.exit_common import (
    ENV_EXIT_PANIC_FROM_ATTEMPT,
    ENV_EXIT_RETRY_MAX_ATTEMPTS,
)
from hunter_meme_executor.exits import exits_once

from .test_live_persistence import (
    MINT,
    FakeRedis,
    Harness,
    _context,
    _fixture,
    _full_token_context,
    _plant_proposal,
    _rows,
    _signer,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration]


class _Err:
    ok = False
    err: Any = {"InstructionError": [2, {"Custom": 6003}]}


class _Ok:
    ok = True
    err: Any = None


def _simulate_6003(_tx: bytes, **_k: Any) -> _Err:
    return _Err()


def _simulate_ok(_tx: bytes, **_k: Any) -> _Ok:
    return _Ok()


@pytest_asyncio.fixture
async def live_harness(
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[Harness]:
    """``test_live_persistence.harness`` reconstruída aqui (uma fixture importada
    com o nome de um parâmetro de teste é F811 no ruff)."""
    import hunter_meme_executor.admission_context as admission_context_module
    import hunter_meme_executor.exits as exits_module

    async def token_context(
        _session: AsyncSession, _mint: str, *, now: datetime | None = None
    ) -> Any:
        return _full_token_context(now or datetime.now(UTC))

    monkeypatch.setattr(admission_context_module, "token_context", token_context)
    monkeypatch.setattr(exits_module, "token_context", token_context)
    async with db_engine.begin() as connection:
        await connection.execute(text("DELETE FROM meme_live_positions"))
        await connection.execute(text("DELETE FROM meme_live_orders"))
        await connection.execute(
            text(
                "DELETE FROM meme_proposals WHERE mode = 'live' "
                "OR (status = 'proposed' AND mint = :mint)"
            ),
            {"mint": MINT},
        )
        await connection.execute(
            text("DELETE FROM meme_risk_snapshots WHERE mint = :mint"), {"mint": MINT}
        )
        await connection.execute(
            text(
                "UPDATE meme_live_kill_switch SET state = 'ACTIVE', reason = NULL, "
                "latched_at = NULL, released_at = NULL, released_by = NULL WHERE scope = 'wallet'"
            )
        )
    yield _context(db_session_factory, _signer(), FakeRedis())


async def _sells(db_engine: AsyncEngine, proposal_id: str) -> list[dict[str, Any]]:
    return await _rows(
        db_engine,
        "SELECT * FROM meme_live_orders WHERE proposal_id = :p AND side = 'sell' ORDER BY attempt",
        p=proposal_id,
    )


async def _failed_first_attempt(
    live: Harness, db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> tuple[Harness, str]:
    """Uma posição aberta cuja **primeira venda falhou** (``6003`` na simulação),
    e nenhuma regra a pedir saída agora: o operador pediu ``sell_now``, a venda
    falhou, o pedido foi atendido (a linha já não o carrega) e a curva não se
    mexeu — nem alvo, nem trailing, nem tempo. É a banda morta de GAMON."""
    proposal_id = await _plant_proposal(db_engine, decided_at=datetime.now(UTC))
    await entries_once(live.ctx)
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE meme_live_positions "
                "SET params = params || '{\"max_hold_s\": 100000000}'::jsonb, "
                "    sell_requested_at = now(), sell_requested_by = 'everton' "
                "WHERE proposal_id = :p"
            ),
            {"p": proposal_id},
        )
    # "Restart": contexto novo sobre as mesmas linhas, com os tokens na cadeia.
    restarted = _context(db_session_factory, _signer(), live.redis)
    restarted.chain.tokens_on_chain = 10**9
    restarted.rpc.transaction = json.loads(json.dumps(_fixture("rpc_tx_probe_raw.json")["result"]))
    restarted.rpc.simulate_transaction = _simulate_6003  # type: ignore[method-assign]
    await exits_once(restarted.ctx)
    sells = await _sells(db_engine, proposal_id)
    assert len(sells) == 1 and sells[0]["status"] == "failed", sells
    assert sells[0]["reason"].startswith("simulation_failed:"), sells[0]["reason"]
    assert restarted.rpc.sent == [], "uma simulação falhada nunca é enviada"
    # o gatilho passou: sem isto o ``sell_now`` voltaria a disparar sozinho
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE meme_live_positions SET sell_requested_at = NULL, "
                "sell_requested_by = NULL WHERE proposal_id = :p"
            ),
            {"p": proposal_id},
        )
    restarted.rpc.simulate_transaction = _simulate_ok  # type: ignore[method-assign]
    return restarted, proposal_id


async def _rewind_backoff(db_engine: AsyncEngine, proposal_id: str) -> None:
    """O backoff passou (``BACKOFF_S[0]`` = 2 s), sem dormir no teste."""
    past = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE meme_live_positions SET exit_intent = "
                "jsonb_set(exit_intent, '{next_attempt_at}', to_jsonb(CAST(:past AS text))) "
                "WHERE proposal_id = :p"
            ),
            {"p": proposal_id, "past": past},
        )


async def test_a_failed_sell_is_retried_by_the_tick_even_when_no_rule_fires_again(
    live_harness: Harness,
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    live, proposal_id = await _failed_first_attempt(live_harness, db_engine, db_session_factory)
    intent = (
        await _rows(
            db_engine,
            "SELECT exit_intent FROM meme_live_positions WHERE proposal_id = :p",
            p=proposal_id,
        )
    )[0]["exit_intent"]
    assert intent["reason"] == "sell_now" and intent["failed"].startswith("simulation_failed:")

    # Antes do backoff: a intenção está pendente, mas ninguém reenvia cedo demais.
    await exits_once(live.ctx)
    assert len(await _sells(db_engine, proposal_id)) == 1, "o backoff foi respeitado"

    await _rewind_backoff(db_engine, proposal_id)
    await exits_once(live.ctx)

    sells = await _sells(db_engine, proposal_id)
    assert len(sells) == 2, sells
    assert sells[1]["attempt"] == 2 and sells[1]["status"] == "confirmed"
    assert sells[1]["client_order_id"] == f"meme:{proposal_id}:exit:2", (
        "chave nova, nunca reassinada"
    )
    assert sells[1]["intent"]["exit_reason"] == "sell_now", "o motivo original, não um inventado"
    assert sells[1]["intent"]["max_slippage_bps"] == 500, "a escada de hoje não mudou"
    closed = await _rows(
        db_engine, "SELECT * FROM meme_live_positions WHERE proposal_id = :p", p=proposal_id
    )
    assert closed[0]["status"] == "closed" and closed[0]["exit"]["reason"] == "sell_now"


async def test_without_the_env_the_tick_leaves_the_failed_sell_where_it_was(
    live_harness: Harness,
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``MEME_EXIT_RETRY_MAX_ATTEMPTS=0`` devolve exatamente o comportamento de
    antes da T4.88 — o que a mesa rodou até 23/09 (e o que este teste prova ser
    um buraco: a posição fica aberta com a saída decidida e ninguém a executa)."""
    live, proposal_id = await _failed_first_attempt(live_harness, db_engine, db_session_factory)
    await _rewind_backoff(db_engine, proposal_id)
    monkeypatch.setenv(ENV_EXIT_RETRY_MAX_ATTEMPTS, "0")
    await exits_once(live.ctx)
    assert len(await _sells(db_engine, proposal_id)) == 1
    open_rows = await _rows(
        db_engine, "SELECT status FROM meme_live_positions WHERE proposal_id = :p", p=proposal_id
    )
    assert open_rows[0]["status"] == "open"


async def test_the_owner_can_put_the_panic_tolerance_on_the_retry(
    live_harness: Harness,
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live, proposal_id = await _failed_first_attempt(live_harness, db_engine, db_session_factory)
    await _rewind_backoff(db_engine, proposal_id)
    monkeypatch.setenv(ENV_EXIT_PANIC_FROM_ATTEMPT, "2")
    await exits_once(live.ctx)
    sells = await _sells(db_engine, proposal_id)
    assert len(sells) == 2 and sells[1]["status"] == "confirmed"
    assert sells[1]["intent"]["max_slippage_bps"] == 1_500
    assert sells[0]["intent"]["max_slippage_bps"] == 500, "a primeira tentativa não foi tocada"


async def test_the_automatic_retry_stops_at_the_cap_and_says_so_by_name(
    live_harness: Harness,
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """O teto limita o reenvio **sem gatilho novo**; bloqueado significa ainda
    exposto, e a posição continua aberta e nomeada no heartbeat."""
    live, proposal_id = await _failed_first_attempt(live_harness, db_engine, db_session_factory)
    await _rewind_backoff(db_engine, proposal_id)
    monkeypatch.setenv(ENV_EXIT_RETRY_MAX_ATTEMPTS, "1")
    await exits_once(live.ctx)
    assert len(await _sells(db_engine, proposal_id)) == 1
    rows = await _rows(
        db_engine,
        "SELECT id, status, exit_intent FROM meme_live_positions WHERE proposal_id = :p",
        p=proposal_id,
    )
    assert rows[0]["status"] == "open"
    assert rows[0]["exit_intent"]["blocked"] == "exit_retry_exhausted"
    assert live.ctx.state.blocked_exits[str(rows[0]["id"])] == "exit_retry_exhausted"
    # e não repete a marcação a cada tick
    await exits_once(live.ctx)
    assert live.ctx.state.exits_blocked == 1
    # Astra (revisão do diff): depois de um restart o bloqueio continua no
    # heartbeat — lido da intenção durável, sem regravar nem recontar.
    again = _context(db_session_factory, _signer(), live.redis)
    again.chain.tokens_on_chain = 10**9
    await exits_once(again.ctx)
    assert again.ctx.state.blocked_exits == {str(rows[0]["id"]): "exit_retry_exhausted"}
    assert again.ctx.state.exits_blocked == 0
    assert len(await _sells(db_engine, proposal_id)) == 1


async def test_a_failure_found_by_the_reconciliation_is_retried_too(
    live_harness: Harness,
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A reconciliação de 30 s (``main.reconcile_once``) passa a ordem para
    ``failed`` sem tocar na intenção: a linha fica com a intenção gravada antes
    do envio, sem ``failed`` e sem ``next_attempt_at``. O gatilho é a ordem."""
    live, proposal_id = await _failed_first_attempt(live_harness, db_engine, db_session_factory)
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE meme_live_positions SET exit_intent = exit_intent - 'failed' "
                "- 'next_attempt_at' WHERE proposal_id = :p"
            ),
            {"p": proposal_id},
        )
    await exits_once(live.ctx)
    sells = await _sells(db_engine, proposal_id)
    assert len(sells) == 2 and sells[1]["status"] == "confirmed", sells
    assert sells[1]["intent"]["exit_reason"] == "sell_now"


# --- T4.90: a sell that landed in its last valid block is a closed position ---

LANDED_SIG = b58encode(b"\x07" * 64)


async def _signed_sell(
    db_engine: AsyncEngine, proposal_id: str, *, status: str, reason: str
) -> None:
    """Turn attempt 1 into a sell that was signed and sent (``last_valid`` 50,
    below the fake chain's height of 100) and left in ``status``."""
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE meme_live_orders SET status = :status, reason = :reason, "
                "  signatures = CAST(:sigs AS jsonb), tx_signature = :sig, "
                "  last_valid_block_height = 50, submitted_at = now() "
                "WHERE proposal_id = :p AND side = 'sell' AND attempt = 1"
            ),
            {
                "p": proposal_id,
                "status": status,
                "reason": reason,
                "sigs": json.dumps([LANDED_SIG]),
                "sig": LANDED_SIG,
            },
        )


def _seen_on_the_second_look(live: Harness) -> list[str]:
    """``getSignatureStatuses``: not visible on the first read, ``confirmed`` after."""
    calls: list[str] = []

    def statuses(signatures: list[str]) -> list[dict[str, Any] | None]:
        calls.append("status")
        if len(calls) == 1:
            return [None]
        return [{"confirmationStatus": "confirmed", "err": None} for _ in signatures]

    live.rpc.get_signature_statuses = statuses  # type: ignore[method-assign]
    return calls


async def test_a_sell_that_landed_in_its_last_valid_block_closes_the_position(
    live_harness: Harness,
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The reconcile read the status (``None``), then the height (past
    ``last_valid``) and wrote ``failed`` — the transaction had landed in between.
    Now the second look finds it: ``confirmed`` with the chain's fill, the
    position closed, nothing sent."""
    live, proposal_id = await _failed_first_attempt(live_harness, db_engine, db_session_factory)
    await _signed_sell(
        db_engine, proposal_id, status="submitted_unconfirmed", reason="confirmation_timeout"
    )
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE meme_live_positions SET sell_requested_at = now(), "
                "sell_requested_by = 'everton' WHERE proposal_id = :p"
            ),
            {"p": proposal_id},
        )
    live.chain.tokens_on_chain = 0
    calls = _seen_on_the_second_look(live)
    await exits_once(live.ctx)
    sells = await _sells(db_engine, proposal_id)
    assert len(sells) == 1 and sells[0]["status"] == "confirmed", sells
    assert sells[0]["fill"]["signature"] == LANDED_SIG
    assert len(calls) == 2, "status, height, status: the second look decided"
    position = (
        await _rows(
            db_engine, "SELECT * FROM meme_live_positions WHERE proposal_id = :p", p=proposal_id
        )
    )[0]
    assert position["status"] == "closed" and position["exit_order_id"] == sells[0]["id"]
    assert live.rpc.sent == [], "reconciliation never sends"


async def test_an_expired_sell_hidden_behind_a_later_failed_retry_closes_the_position(
    live_harness: Harness,
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Attempt 1 was written ``failed:blockhash_expired_never_landed`` but had
    landed; attempt 2 was built on a stale balance and failed. With the wallet
    empty, the tick asks the chain about attempt 1 — not only the newest row —
    and closes with its fill instead of ``blocked:no_tokens_on_chain``."""
    live, proposal_id = await _failed_first_attempt(live_harness, db_engine, db_session_factory)
    await _signed_sell(
        db_engine, proposal_id, status="failed", reason="blockhash_expired_never_landed"
    )
    await _rewind_backoff(db_engine, proposal_id)
    live.rpc.simulate_transaction = _simulate_6003  # type: ignore[method-assign]
    await exits_once(live.ctx)
    sells = await _sells(db_engine, proposal_id)
    assert [s["status"] for s in sells] == ["failed", "failed"], sells

    live.chain.tokens_on_chain = 0  # the balance catches up: attempt 1 sold everything
    live.rpc.simulate_transaction = _simulate_ok  # type: ignore[method-assign]
    await _rewind_backoff(db_engine, proposal_id)
    await exits_once(live.ctx)
    sells = await _sells(db_engine, proposal_id)
    assert [s["status"] for s in sells] == ["confirmed", "failed"], sells
    position = (
        await _rows(
            db_engine, "SELECT * FROM meme_live_positions WHERE proposal_id = :p", p=proposal_id
        )
    )[0]
    assert position["status"] == "closed" and position["exit_order_id"] == sells[0]["id"]
    assert position["exit"]["reason"] == "sell_now"
    assert live.rpc.sent == [], "nothing was signed or sent to settle it"
    assert not live.ctx.state.blocked_exits
