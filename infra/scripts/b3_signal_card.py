#!/usr/bin/env python3
"""Cartão do dia da H-038 (momento intradiário no WIN) — ferramenta de pesquisa, não produto.

O Everton digita o fechamento oficial anterior e quando o obteve, o Ibovespa da barra que
termina às 10:30 (do histórico do gráfico, nunca a cotação corrente) e quando o leu, e o WIN
atual se quiser; o módulo puro ``hunter_indicators.b3.intraday_momentum`` (o mesmo do painel
e do robô MT5) decide, e o cartão sai em português:

    uv run python infra/scripts/b3_signal_card.py \\
        --fechamento-anterior 130.456,78 --fechamento-lido-as 2026-10-16T18:30 \\
        --ibov-1030 131.002,15 --lido-as 10:42 --win 207150

Horas sem fuso são BRT; ``HH:MM`` é no dia do pregão; ``AAAA-MM-DDTHH:MM`` aceita outro dia e
respeita um fuso explícito (``Z``, ``-03:00``). Nenhuma ordem, nenhuma conta, nenhum tamanho:
o cartão diz direção, janela, stop nominal e saída; quem decide e executa é o Everton (plano
``docs/plans/MERCADO-TRADICIONAL.md`` §1.7).

**Registro durável — escolha documentada (W0-F):** a regra da casa é Postgres e nada local.
Não há tabela B3 no nosso Postgres (o schema é a tarefa W0-4, que espera a aprovação do
desenho W0-2) e ``infra/research`` não tem banco local (lê exportações CSV). Por isso o cartão
termina com **uma linha ``H038|...|sha256=...``** que o Everton cola para a Sexta-feira, que a
grava no diário do Obsidian (versionado no git). Os 16 hex do fim são o sha256 do resto da
linha: uma cola truncada ou alterada não confere. Vale a primeira linha do dia; uma segunda só
registra impedimento ou erro de leitura. Nenhum arquivo é escrito por este script.

Saída 0 = cartão impresso (inclusive SEM OPERAÇÃO); 2 = entrada inválida (só o erro).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import re
import sys
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, date, datetime, time
from decimal import ROUND_HALF_EVEN, Decimal
from typing import TextIO

from hunter_indicators.b3.calendar_2026 import (
    BRT,
    NO_TRADING_DAYS,
    WIN_SPEC,
    OutsideCalendarCoverage,
    b3_session,
    win_contract,
)
from hunter_indicators.b3.contract import (
    IndexReading,
    IndexReadings,
    NoTrade,
    NoTradeReason,
    SessionTimes,
    Side,
    Signal,
)
from hunter_indicators.b3.intraday_momentum import H038_V1, decide_intraday_momentum

SOURCE = "manual:everton"
_DOT_THOUSANDS_ONLY = re.compile(r"\d{1,3}(\.\d{3})+")
_BRAZILIAN = re.compile(r"(\d{1,3}(\.\d{3})+|\d+),\d+")
_PLAIN = re.compile(r"\d+(\.\d+)?")
_TIME = re.compile(r"(\d{1,2})[:h](\d{2})(?::(\d{2}))?")

# Typo guards of this CLI, not part of the rule: B3's last circuit-breaker level is −20 %, and
# the WIN trades at the index plus a carry of a few percent.
_MAX_INDEX_MOVE = Decimal("0.20")
_MAX_WIN_BASIS = Decimal("0.10")

_REASONS = {
    NoTradeReason.SHORTENED_SESSION: "pregão encurtado — excluído antes da entrada pelo pré-registro",
    NoTradeReason.WIN_EXPIRY_DAY: (
        "dia de vencimento do WIN — excluído; opera-se o vencimento seguinte a partir do "
        "pregão seguinte"
    ),
    NoTradeReason.KNOWN_IMPEDIMENT: "impedimento conhecido em O+30 ou C−30 (leilão, interrupção)",
    NoTradeReason.READING_MISSING: "falta a leitura do Ibovespa das 10:30",
    NoTradeReason.PREVIOUS_CLOSE_NOT_PREVIOUS_SESSION: (
        "o fechamento informado não é o do pregão anterior"
    ),
    NoTradeReason.READING_NOT_AT_SIGNAL_TIME: "a leitura não é a da barra que termina às 10:30",
    NoTradeReason.RECEIVED_BEFORE_EVENT: (
        "uma hora de leitura é anterior ao próprio dado — impossível; confira as horas"
    ),
    NoTradeReason.NOT_YET_RECEIVED: (
        "uma hora de leitura é posterior ao instante do cartão — confira as horas"
    ),
    NoTradeReason.RECEIVED_AFTER_DEADLINE: (
        "um dos dois números chegou depois do prazo de {deadline} (O+90): sem sinal hoje"
    ),
    NoTradeReason.ZERO_RETURN: "r1 = 0 — Ibovespa das 10:30 igual ao fechamento anterior",
}


def parse_number(text: str) -> Decimal:
    """``130.456,78`` / ``130456,78`` / ``130456.78`` / ``130456`` → Decimal; nothing else.

    ``130.456`` is refused as ambiguous, and so is any other shape (signs, exponents, an
    English ``131,300.00``) — a wrong number here can flip the direction.
    """
    raw = text.strip()
    if _DOT_THOUSANDS_ONLY.fullmatch(raw):
        raise ValueError(f"número ambíguo {text!r}: escreva 130456,78 ou 130456.78")
    if _BRAZILIAN.fullmatch(raw):
        value = Decimal(raw.replace(".", "").replace(",", "."))
    elif _PLAIN.fullmatch(raw):
        value = Decimal(raw)
    else:
        raise ValueError(f"formato de número não reconhecido {text!r}: use 130456,78 ou 130456.78")
    if value <= 0:
        raise ValueError(f"o número precisa ser positivo: {text!r}")
    return value


def parse_instant(text: str, day: date) -> datetime:
    """``HH:MM[:SS]`` / ``HHhMM`` on ``day`` in BRT, or ISO ``AAAA-MM-DDTHH:MM[offset]``."""
    raw = text.strip()
    match = _TIME.fullmatch(raw)
    if match is not None:
        hour, minute, second = int(match[1]), int(match[2]), int(match[3] or 0)
        if hour > 23 or minute > 59 or second > 59:
            raise ValueError(f"hora inválida {text!r}")
        return datetime.combine(day, time(hour, minute, second), tzinfo=BRT).astimezone(UTC)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        raise ValueError(f"hora inválida {text!r}: use HH:MM ou AAAA-MM-DDTHH:MM") from None
    if "T" not in raw:
        raise ValueError(f"hora inválida {text!r}: falta a hora")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BRT)
    return parsed.astimezone(UTC)


def _group(digits: str) -> str:
    return f"{int(digits):,}".replace(",", ".")


def fmt_points(value: Decimal) -> str:
    return _group(str(value.to_integral_value()))


def _fmt_2dp(value: Decimal) -> str:
    whole, _, cents = f"{value.quantize(Decimal('0.01'), ROUND_HALF_EVEN):f}".partition(".")
    return f"{_group(whole)},{cents}"


def fmt_index(value: Decimal) -> str:
    return _fmt_2dp(value)


def fmt_brl(value: Decimal) -> str:
    return f"R$ {_fmt_2dp(value)}"


def fmt_pct(fraction: Decimal) -> str:
    pct = (fraction * 100).quantize(Decimal("0.0001"), ROUND_HALF_EVEN)
    sign = "+" if pct >= 0 else "−"
    return f"{sign}{f'{abs(pct):f}'.replace('.', ',')} %"


def _brt(instant: datetime) -> str:
    return instant.astimezone(BRT).strftime("%H:%M")


def _z(instant: datetime) -> str:
    return instant.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def record_line(fields: dict[str, str]) -> str:
    body = "H038|" + "|".join(f"{k}={v}" for k, v in fields.items())
    return f"{body}|sha256={hashlib.sha256(body.encode('utf-8')).hexdigest()[:16]}"


def _stop_lines(signal: Signal, win: Decimal | None) -> tuple[list[str], dict[str, str]]:
    if win is None:
        return [
            "Stop de catástrofe: 0,5 % do preço da SUA entrada, arredondado ao tick de 5 pts "
            "(compra: para baixo; venda: para cima). Informe --win para ver em pontos."
        ], {}
    stop = signal.stop_price(win, WIN_SPEC)
    distance = abs(win - stop)
    money = distance * WIN_SPEC.point_value_brl
    return [
        f"Stop de catástrofe: {fmt_points(stop)} pts para WIN de referência {fmt_points(win)} "
        f"(distância {fmt_points(distance)} pts = {fmt_brl(money)} por contrato).",
        "  Distância nominal, não é perda máxima (gap, stop rejeitado ou desconexão passam do nível).",
        "  Recalcule sobre o preço da sua entrada: compra = entrada × 0,995 para baixo; "
        "venda = × 1,005 para cima.",
    ], {"win_ref": f"{win:f}", "stop": f"{stop:f}"}


def _signal_lines(
    session: SessionTimes, signal: Signal, o30: IndexReading, close: Decimal
) -> list[str]:
    word = "COMPRA" if signal.side is Side.BUY else "VENDA"
    relation = "acima do" if signal.side is Side.BUY else "abaixo do"
    start, end = _brt(signal.entry_window_start), _brt(signal.entry_window_end)
    return [
        f"SINAL: {word} — {win_contract(session.trading_date)} "
        "(direção do sinal; posição só depois da sua execução)",
        f"Motivo: r1 = {fmt_pct(signal.r1)} — Ibovespa das 10:30 {fmt_index(o30.value)} "
        f"{relation} fechamento anterior {fmt_index(close)}.",
        f"Entrada: a mercado entre {start} e {end} (BRT); fora da janela = não executado.",
        f"  Impedimento conhecido (leilão, interrupção) às 10:30 ou entre {start} e {end}: não "
        "entre; o pregão é excluído (gere o cartão com --impedimento para registrar).",
    ]


def render(
    session: SessionTimes,
    readings: IndexReadings,
    outcome: Signal | NoTrade,
    win: Decimal | None,
    impediment: str | None,
) -> str:
    o30 = readings.first_half_hour
    assert o30 is not None
    previous = readings.previous_close
    fields = {
        "v": H038_V1.version,
        "data": session.trading_date.isoformat(),
        "F": f"{previous.value:f}",
        "F_recebido": _z(previous.received_at),
        "I": f"{o30.value:f}",
        "I_evento": _z(o30.event_at),
        "recebido": _z(o30.received_at),
        "decisao": _z(readings.decision_at),
    }
    lines = [
        f"CARTÃO DO DIA — H-038 ({H038_V1.version}) — {session.trading_date:%d/%m/%Y}",
        "",
    ]
    if isinstance(outcome, NoTrade):
        deadline = _brt(session.open_at + H038_V1.deadline_offset)
        lines += [
            "SINAL: SEM OPERAÇÃO",
            f"Motivo: {_REASONS[outcome.reason].format(deadline=deadline)}",
        ]
        fields |= {"sinal": "SEM_OPERACAO", "motivo": outcome.reason.value}
        if impediment:
            lines.append(f"Impedimento informado: {impediment}")
            fields["impedimento"] = impediment
    else:
        stop_lines, stop_fields = _stop_lines(outcome, win)
        lines += _signal_lines(session, outcome, o30, previous.value)
        lines += stop_lines
        lines += [
            "  Stop tocado: acabou o dia — sem reentrada.",
            f"Saída: zerar a mercado às {_brt(outcome.exit_at)} (BRT). Sem alvo — saída por tempo.",
            "Depois da saída, confira posição e ordens abertas na plataforma "
            "(stop independente pode abrir posição inversa).",
        ]
        fields |= {
            "sinal": "COMPRA" if outcome.side is Side.BUY else "VENDA",
            "r1": str(outcome.r1),
        }
        fields |= stop_fields | {"motivo": outcome.reason}
    lines += [
        f"Fechamento anterior recebido em {previous.received_at.astimezone(BRT):%d/%m %H:%M}; "
        f"leitura das 10:30 às {_brt(o30.received_at)}; cartão às {_brt(readings.decision_at)} (BRT).",
        "Vantagem no WIN não demonstrada: H-038 está aberta e o rótulo só sai do teste pré-registrado.",
        "Tamanho: decisão sua. Nenhum agente envia ordem nem toca a conta.",
        "",
        "REGISTRO — cole esta linha para a Sexta-feira (Vale a primeira linha do dia; outra só "
        "registra impedimento ou erro de leitura):",
        record_line(fields),
    ]
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Cartão do dia da H-038 (WIN, B3).")
    p.add_argument("--data", help="pregão AAAA-MM-DD (padrão: hoje em BRT)")
    p.add_argument("--fechamento-anterior", required=True, help="fechamento oficial anterior")
    p.add_argument(
        "--fechamento-lido-as", required=True, help="quando você obteve o fechamento anterior"
    )
    p.add_argument("--ibov-1030", required=True, help="Ibovespa na barra que termina às 10:30")
    p.add_argument("--lido-as", required=True, help="quando você leu o valor das 10:30")
    p.add_argument("--win", help="preço atual do WIN em pontos (para o stop em pontos)")
    p.add_argument("--impedimento", help="leilão ou interrupção conhecida às 10:30 ou na janela")
    p.add_argument("--agora", help="instante do cartão (padrão: o relógio)")
    return p


def _checked_inputs(ns: argparse.Namespace) -> tuple[Decimal, Decimal, Decimal | None]:
    close, o30 = parse_number(ns.fechamento_anterior), parse_number(ns.ibov_1030)
    if abs(o30 / close - 1) > _MAX_INDEX_MOVE:
        raise ValueError(
            f"Ibovespa das 10:30 ({ns.ibov_1030}) e fechamento anterior ({ns.fechamento_anterior}) "
            "diferem mais de 20 % — confira os números"
        )
    win = parse_number(ns.win) if ns.win else None
    if win is not None and win % WIN_SPEC.tick_size != 0:
        raise ValueError(f"o preço do WIN precisa ser múltiplo de {WIN_SPEC.tick_size} pontos")
    if win is not None and abs(win / o30 - 1) > _MAX_WIN_BASIS:
        raise ValueError(f"WIN {ns.win} longe do Ibovespa {ns.ibov_1030} — confira os números")
    return close, o30, win


def _decide(ns: argparse.Namespace) -> str:
    now = datetime.now(UTC)
    day = date.fromisoformat(ns.data) if ns.data else now.astimezone(BRT).date()
    try:
        session = b3_session(day)
    except OutsideCalendarCoverage as exc:
        raise ValueError(f"o calendário B3 do módulo não cobre {day:%d/%m/%Y}: {exc}") from None
    if session is None:
        why = NO_TRADING_DAYS.get(day, "fim de semana")
        return (
            f"CARTÃO DO DIA — H-038 — {day:%d/%m/%Y}\n\n"
            f"SINAL: SEM OPERAÇÃO\nMotivo: a B3 não tem pregão ({why}).\n"
        )
    close, o30_value, win = _checked_inputs(ns)
    impediment = " ".join(ns.impedimento.replace("|", "/").split()) if ns.impedimento else None
    if impediment:
        session = replace(session, exclusions=(*session.exclusions, NoTradeReason.KNOWN_IMPEDIMENT))
    previous = IndexReading(
        close, session.previous_close_at, parse_instant(ns.fechamento_lido_as, day), SOURCE
    )
    o30 = IndexReading(
        o30_value,
        session.open_at + H038_V1.signal_offset,
        parse_instant(ns.lido_as, day),
        SOURCE,
    )
    decision_at = parse_instant(ns.agora, day) if ns.agora else now
    readings = IndexReadings(previous, o30, decision_at)
    outcome = decide_intraday_momentum(readings, session, H038_V1)
    return render(session, readings, outcome, win, impediment)


def main(argv: Sequence[str] | None = None, out: TextIO = sys.stdout) -> int:
    if isinstance(out, io.TextIOWrapper):
        out.reconfigure(encoding="utf-8")  # a Windows pipe defaults to cp1252, which has no "−"
    ns = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        text = _decide(ns)
    except ValueError as exc:
        out.write(f"ERRO: {exc}\n")
        return 2
    out.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
