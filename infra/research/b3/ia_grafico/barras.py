"""Barras do WIN, a janela causal de um instante *t* e a dobra de 1 min em 5 min.

Regra de antecipação (KB-0149 §5 item 24): a imagem de *t* só pode conter barras **finais**
cujo **fim** é ≤ *t*. ``janela_causal`` seleciona; ``exigir_causal`` é a segunda trava, usada
pelo desenho da imagem, e recusa com ``AntecipacaoError`` qualquer janela que a viole.

Preços em ``Decimal`` (fronteira com dinheiro), validados em runtime; instantes sempre UTC
*aware*; a data do pregão é a data no fuso histórico de São Paulo.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

BRT = ZoneInfo("America/Sao_Paulo")
"""Fuso histórico de São Paulo (com os horários de verão até 2019), nunca UTC−3 fixo."""

UM_MINUTO = timedelta(minutes=1)


class AntecipacaoError(ValueError):
    """Uma barra posterior a *t* (ou não final) tentou entrar na imagem de *t*."""


class BaldeIncompletoError(ValueError):
    """Minuto ausente dentro do pregão: ausência de linha não prova ausência de negócio."""


def utc(valor: datetime, nome: str) -> datetime:
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise ValueError(f"{nome} precisa ser timezone-aware (UTC)")
    return valor.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class Barra:
    inicio: datetime
    duracao: timedelta
    abertura: Decimal
    maxima: Decimal
    minima: Decimal
    fechamento: Decimal
    volume: Decimal
    final: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "inicio", utc(self.inicio, "inicio"))
        for nome in ("abertura", "maxima", "minima", "fechamento", "volume"):
            valor: object = getattr(self, nome)
            if not isinstance(valor, Decimal):
                raise TypeError(f"{nome} precisa ser Decimal, veio {type(valor).__name__}")
            if not valor.is_finite():
                raise ValueError(f"{nome} precisa ser finito")
        if self.duracao <= timedelta(0):
            raise ValueError("duracao precisa ser positiva")
        o, h, lo, c = self.abertura, self.maxima, self.minima, self.fechamento
        if not (lo <= min(o, c) and h >= max(o, c) and lo > 0):
            raise ValueError(f"OHLC incoerente em {self.inicio.isoformat()}: {o} {h} {lo} {c}")
        if self.volume < 0:
            raise ValueError("volume negativo")

    @property
    def fim(self) -> datetime:
        return self.inicio + self.duracao


def data_pregao(instante: datetime) -> object:
    return instante.astimezone(BRT).date()


def janela_causal(barras: Iterable[Barra], t: datetime) -> tuple[Barra, ...]:
    """As barras finais com fim ≤ *t*, em ordem de início. A barra que atravessa *t* fica fora."""
    t = utc(t, "t")
    return tuple(sorted((b for b in barras if b.final and b.fim <= t), key=lambda b: b.inicio))


def exigir_causal(janela: Sequence[Barra], t: datetime) -> None:
    t = utc(t, "t")
    for b in janela:
        if not b.final:
            raise AntecipacaoError(f"barra não final em {b.inicio.isoformat()}")
        if b.fim > t:
            raise AntecipacaoError(
                f"barra que termina em {b.fim.isoformat()} depois de t={t.isoformat()}"
            )


def dobrar(barras: Sequence[Barra], t: datetime, *, minutos: int) -> tuple[Barra, ...]:
    """Dobra barras causais de 1 min em baldes de ``minutos``.

    Balde = [início alinhado ao relógio, + minutos), e só existe **completo**: os ``minutos``
    minutos presentes, sem duplicata. Balde que termina depois de *t* é descartado (nunca entra
    parcial). Balde com minuto faltando, ou balde inteiro faltando entre dois do mesmo pregão,
    levanta ``BaldeIncompletoError`` — a janela fica indisponível, nunca preenchida.
    """
    if minutos <= 0 or 60 % minutos:
        raise ValueError("minutos precisa ser positivo e dividir a hora")
    t = utc(t, "t")
    exigir_causal(barras, t)
    passo = timedelta(minutes=minutos)
    baldes: dict[datetime, list[Barra]] = {}
    vistos: set[datetime] = set()
    for b in sorted(barras, key=lambda x: x.inicio):
        if b.duracao != UM_MINUTO:
            raise ValueError(f"barra de entrada precisa ter 1 min: {b.inicio.isoformat()}")
        if b.inicio.second or b.inicio.microsecond:
            raise ValueError(f"barra de 1 min não alinhada ao minuto: {b.inicio.isoformat()}")
        if b.inicio in vistos:
            raise ValueError(f"barra duplicada em {b.inicio.isoformat()}")
        vistos.add(b.inicio)
        chave = b.inicio.replace(
            minute=b.inicio.minute - b.inicio.minute % minutos, second=0, microsecond=0
        )
        baldes.setdefault(chave, []).append(b)
    saida: list[Barra] = []
    for inicio, grupo in sorted(baldes.items()):
        if inicio + passo > t:
            continue
        if len(grupo) != minutos:
            raise BaldeIncompletoError(
                f"balde de {inicio.isoformat()} com {len(grupo)} de {minutos} minutos"
            )
        anterior = saida[-1].inicio if saida else None
        if anterior and data_pregao(anterior) == data_pregao(inicio) and inicio - anterior != passo:
            raise BaldeIncompletoError(
                f"buraco entre {anterior.isoformat()} e {inicio.isoformat()}"
            )
        saida.append(
            Barra(
                inicio=inicio,
                duracao=passo,
                abertura=grupo[0].abertura,
                maxima=max(b.maxima for b in grupo),
                minima=min(b.minima for b in grupo),
                fechamento=grupo[-1].fechamento,
                volume=sum((b.volume for b in grupo), Decimal(0)),
            )
        )
    return tuple(saida)
