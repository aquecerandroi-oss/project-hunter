"""T4.88 — a saída que falhou continua devida, e a escada de slippage por tentativa.

Medido nas 101 vendas reais da mesa (17→23/09, leitura read-only da VPS,
reconstrução da fita pelo método do R62/R64; números em
``docs/RISK_ENGINE_MEME.md``, parágrafo T4.88):

- **GAMON, 21/09.** A tentativa 1 (motivo ``target``, 5 %) falhou com ``6003``
  às 12:31:02,58. O preço caiu para a banda morta — abaixo do alvo, 9,5 % abaixo
  do pico, com o trailing em 10 % — e **nenhuma regra disparou**. Como
  ``decide_exit`` é sem memória e ``route_exit`` só é chamado quando uma regra
  dispara, o ``next_attempt_at``/``BACKOFF_S`` que a falha escreveu ficou sem
  leitor: a tentativa 2 só saiu 17,4 s depois, quando o trailing finalmente
  armou, e a marca já tinha caído de 0,0803 para 0,0724 (−0,0079 SOL). É o maior
  item medido do período. O contrato (``docs/RISK_ENGINE_MEME.md``, "A tentativa
  acaba, a intenção não") diz o contrário do que o código fazia.
- **Escada por tentativa (desligada por omissão).** A tentativa 2 de GAMON falhou
  de novo com os mesmos 5 % (+0,0031 SOL se tivesse usado o pânico); a de PS,
  −0,0001. Dois casos não estabelecem retorno esperado (e o de GAMON é o mesmo
  caso do defeito acima — os dois ganhos **não se somam**), por isso o padrão de
  ``MEME_EXIT_PANIC_FROM_ATTEMPT`` é ``0`` = a escada de hoje. ``=2`` escala na
  retentativa, ``=1`` dá a hipótese do dono (pânico já na 1.ª tentativa).
- **O que NÃO mudou:** a 1.ª tentativa de uma saída calma continua com 5 % e a de
  ``creator_dump``/``rug_signal`` continua com 15 % — medido, o pânico na 1.ª
  tentativa dos motivos violentos vale +0,0002 SOL em 7 dias (o ``creator_dump``
  já é pânico hoje; na própria AIRAA a espera não custou nada: a marca ficou
  parada em ~0,0145 do segundo do dump até 70 s depois).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_meme_executor.exit_common import (
    ENV_EXIT_PANIC_FROM_ATTEMPT,
    ENV_EXIT_RETRY_MAX_ATTEMPTS,
    exit_retry_exhausted,
    retry_reason,
    sell_slippage_bps,
)
from hunter_meme_executor.send_tuning import SendTuning

NOW = datetime(2026, 9, 21, 12, 31, 5, tzinfo=UTC)
CALM = ("target", "trailing", "time_stop", "sell_now", "emergency_auto_close")
VIOLENT = ("creator_dump", "rug_signal")


def _intent(**overrides: Any) -> dict[str, Any]:
    intent: dict[str, Any] = {
        "reason": "target",
        "decided_at": (NOW - timedelta(seconds=5)).isoformat(),
        "attempt": 1,
        "failed": "onchain_error:{'InstructionError': [2, {'Custom': 6003}]}",
        "next_attempt_at": (NOW - timedelta(seconds=1)).isoformat(),
    }
    intent.update(overrides)
    return intent


# --- a escada de slippage por tentativa -------------------------------------


@pytest.mark.parametrize("reason", CALM)
def test_the_first_attempt_of_a_calm_exit_keeps_the_five_per_cent_of_today(reason: str) -> None:
    assert sell_slippage_bps(SendTuning(), reason, attempt=1, env={}) == 500


@pytest.mark.parametrize("reason", VIOLENT)
def test_the_first_attempt_of_a_violent_exit_is_panic_as_it_already_was(reason: str) -> None:
    assert sell_slippage_bps(SendTuning(), reason, attempt=1, env={}) == 1_500


@pytest.mark.parametrize("attempt", [1, 2, 3, 9])
def test_by_default_the_ladder_is_exactly_the_one_of_today(attempt: int) -> None:
    """A medição não estabelece retorno esperado para escalar (2 casos, um só
    deles positivo): o padrão continua o de hoje e a escada é uma decisão de
    política do dono, alcançável por env."""
    for reason in CALM:
        assert sell_slippage_bps(SendTuning(), reason, attempt=attempt, env={}) == 500, reason
    for reason in VIOLENT:
        assert sell_slippage_bps(SendTuning(), reason, attempt=attempt, env={}) == 1_500, reason


@pytest.mark.parametrize("attempt", [2, 3, 6])
def test_from_two_the_retry_escalates_to_the_panic_tolerance(attempt: int) -> None:
    env = {ENV_EXIT_PANIC_FROM_ATTEMPT: "2"}
    for reason in CALM + VIOLENT:
        assert sell_slippage_bps(SendTuning(), reason, attempt=attempt, env=env) == 1_500, reason
    for reason in CALM:  # a primeira tentativa não muda
        assert sell_slippage_bps(SendTuning(), reason, attempt=1, env=env) == 500, reason


def test_the_owner_can_ask_for_panic_on_the_first_attempt() -> None:
    env = {ENV_EXIT_PANIC_FROM_ATTEMPT: "1"}
    for reason in CALM + VIOLENT:
        assert sell_slippage_bps(SendTuning(), reason, attempt=1, env=env) == 1_500, reason


def test_the_ladder_never_goes_above_the_configured_panic_cap() -> None:
    tuning = SendTuning(exit_max_slippage_pct=Decimal(3), panic_exit_max_slippage_pct=Decimal(8))
    for env in ({}, {ENV_EXIT_PANIC_FROM_ATTEMPT: "1"}, {ENV_EXIT_PANIC_FROM_ATTEMPT: "2"}):
        for attempt in range(1, 11):
            for reason in CALM + VIOLENT:
                assert sell_slippage_bps(tuning, reason, attempt=attempt, env=env) <= 800, reason
    escalating = {ENV_EXIT_PANIC_FROM_ATTEMPT: "2"}
    assert sell_slippage_bps(tuning, "trailing", attempt=1, env=escalating) == 300
    assert sell_slippage_bps(tuning, "trailing", attempt=2, env=escalating) == 800
    # Astra (revisão do diff): normal 20 % acima de um pânico de 15 % — a escada
    # aplica exatamente o pânico, nunca ``max(normal, pânico)`` = 20 %.
    inverted = SendTuning(
        exit_max_slippage_pct=Decimal(20), panic_exit_max_slippage_pct=Decimal(15)
    )
    assert sell_slippage_bps(inverted, "trailing", attempt=2, env=escalating) == 1_500
    assert sell_slippage_bps(inverted, "trailing", attempt=1, env=escalating) == 2_000, (
        "a primeira tentativa continua a de hoje, por motivo"
    )


def test_a_nonsense_value_falls_back_to_the_default_and_never_refuses() -> None:
    for raw in ("", "   ", "sim", "-3", "1.5"):
        env = {ENV_EXIT_PANIC_FROM_ATTEMPT: raw}
        assert sell_slippage_bps(SendTuning(), "trailing", attempt=1, env=env) == 500, raw
        assert sell_slippage_bps(SendTuning(), "trailing", attempt=2, env=env) == 500, raw


# --- a intenção que sobrevive à tentativa falhada ---------------------------
# ``retry_reason`` é a leitura da intenção; quem diz que a tentativa **falhou** é
# a linha durável da ordem (``pending_sell_retry``, testada na integração) — a
# falha descoberta pelo laço de reconciliação de 30 s nunca escreve ``failed``
# na intenção (``main.reconcile_once``), e era esse o furo da revisão da Astra.


def test_a_decided_exit_past_its_backoff_is_still_owed_the_sell() -> None:
    assert retry_reason(_intent(), NOW, env={}) == "target"
    # a intenção gravada antes do envio (a falha veio da reconciliação) também
    clean = {"reason": "trailing", "decided_at": NOW.isoformat(), "attempt": 1, "order_key": "k"}
    assert retry_reason(clean, NOW, env={}) == "trailing"


def test_the_backoff_is_respected() -> None:
    intent = _intent(next_attempt_at=(NOW + timedelta(seconds=1)).isoformat())
    assert retry_reason(intent, NOW, env={}) is None


def test_without_a_decided_exit_there_is_nothing_to_resend() -> None:
    assert retry_reason(None, NOW, env={}) is None
    assert retry_reason({}, NOW, env={}) is None
    # nem a recusa nomeada de ``mark_blocked`` (o motivo do bloqueio manda)
    blocked = {"reason": "trailing", "decided_at": NOW.isoformat(), "blocked": "curve_complete"}
    assert retry_reason(blocked, NOW, env={}) is None


def test_a_reason_the_engine_does_not_know_is_never_resent() -> None:
    assert retry_reason(_intent(reason="porque_sim"), NOW, env={}) is None


def test_a_broken_timestamp_is_not_a_retry_and_a_missing_one_is_due_now() -> None:
    assert retry_reason(_intent(next_attempt_at="ontem"), NOW, env={}) is None
    assert retry_reason(_intent(next_attempt_at=None), NOW, env={}) == "target"


def test_the_retries_are_capped_and_the_cap_is_named() -> None:
    at_cap = _intent(attempt=6)
    assert retry_reason(at_cap, NOW, env={}) is None
    assert exit_retry_exhausted(at_cap, env={}) is True
    assert exit_retry_exhausted(_intent(attempt=5), env={}) is False
    assert exit_retry_exhausted(None, env={}) is False
    tight = {ENV_EXIT_RETRY_MAX_ATTEMPTS: "1"}
    assert retry_reason(_intent(attempt=1), NOW, env=tight) is None
    assert exit_retry_exhausted(_intent(attempt=1), env=tight) is True


def test_the_retry_can_be_turned_off_entirely() -> None:
    off = {ENV_EXIT_RETRY_MAX_ATTEMPTS: "0"}
    assert retry_reason(_intent(), NOW, env=off) is None
    assert exit_retry_exhausted(_intent(), env=off) is False
