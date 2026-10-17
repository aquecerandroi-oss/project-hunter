"""Simulação de uma ordem nas barras de 1 min **depois** de *t* (aproximação OHLC, rotulada).

Regras (desenho §1.4, com os ajustes da Astra R1), todas conservadoras:

- entrada a mercado: abertura da 1.ª barra que começa em *t* + 1 min, dentro de 5 min e antes do
  fim da sessão; limite: válido 30 min, só preenche com **travessia** de 1 tick;
- na barra do fill de um limite só o stop vale (a ordem dentro da barra é desconhecida);
- stop dispara com toque igual, gap além do stop sai na abertura; alvo só com travessia;
  stop e alvo na mesma barra → stop;
- fill além do stop ou do alvo (gap na entrada) → sai na hora, sem ganho;
- saída por tempo na abertura da 1.ª barra em min(fill + 60 min, fim da sessão); nenhuma
  máxima/mínima dessa barra decide nada;
- 1 tick adverso em **toda** perna, pelo lado, e R$ 0,256 por perna; minuto ausente durante a
  posição (ou na janela do limite) → **censura**; o cenário condicionado (stop + 1 tick) não é
  limite — o veredito não decide com ele.

Preços em ``Decimal``; bp contra o fechamento de referência (nocional comum a todos os braços).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from infra.research.b3.ia_grafico.barras import UM_MINUTO, Barra, utc
from infra.research.b3.ia_grafico.protocolo import (
    ATRASO_DECISAO,
    CUSTO_PERNA_PTS,
    DESLIZE_TICKS,
    HORIZONTE,
    TICK,
    TOLERANCIA_ENTRADA,
    VALIDADE_LIMITE,
)
from infra.research.b3.ia_grafico.resposta import Lado

DESLIZE = TICK * DESLIZE_TICKS
CUSTO_IDA_VOLTA = 2 * CUSTO_PERNA_PTS


class Status(StrEnum):
    OK = "ok"
    SEM_FILL = "sem_fill"
    SEM_PRECO_ENTRADA = "sem_preco_entrada"
    CENSURADO = "censurado"


@dataclass(frozen=True, slots=True)
class Ordem:
    """Níveis absolutos (stop/alvo, da resposta da IA) **ou** ``distancia`` simétrica ao fill."""

    lado: Lado
    tipo: str
    stop: Decimal | None = None
    alvo: Decimal | None = None
    limite: Decimal | None = None
    distancia: Decimal | None = None

    def __post_init__(self) -> None:
        if self.lado is Lado.NENHUM or self.tipo not in ("market", "limit"):
            raise ValueError("ordem precisa de lado compra/venda e tipo market/limit")
        if (self.distancia is None) == (self.stop is None or self.alvo is None):
            raise ValueError("use stop+alvo absolutos ou distancia, nunca os dois")
        if (self.tipo == "limit") != (self.limite is not None):
            raise ValueError("limite só (e sempre) com tipo limit")
        if self.distancia is not None and self.tipo == "limit":
            raise ValueError("distancia só com entrada a mercado (braço direcional)")


@dataclass(frozen=True, slots=True)
class Contexto:
    t: datetime
    fim_sessao: datetime
    referencia: Decimal
    horizonte: timedelta = HORIZONTE
    atraso: timedelta = ATRASO_DECISAO


@dataclass(frozen=True, slots=True)
class Resultado:
    status: Status
    motivo: str | None = None
    inicio: datetime | None = None
    fim: datetime | None = None
    entrada: Decimal | None = None
    saida: Decimal | None = None
    stop: Decimal | None = None
    alvo: Decimal | None = None
    net_pts: Decimal | None = None
    pior_caso_pts: Decimal | None = None
    referencia: Decimal = field(default=Decimal(1))

    @property
    def net_bp(self) -> float | None:
        if self.net_pts is None:
            return None
        return float(self.net_pts / self.referencia * 10_000)


def _sentido(lado: Lado) -> int:
    return 1 if lado is Lado.COMPRA else -1


def simular(barras: Sequence[Barra], ordem: Ordem, ctx: Contexto) -> Resultado:
    t, fim_sessao = utc(ctx.t, "t"), utc(ctx.fim_sessao, "fim_sessao")
    s = _sentido(ordem.lado)
    futuras = sorted(
        (b for b in barras if b.final and b.inicio >= t + ctx.atraso), key=lambda b: b.inicio
    )
    inicio_janela = t + ctx.atraso
    if ordem.tipo == "market":
        if not futuras or futuras[0].inicio > inicio_janela + TOLERANCIA_ENTRADA:
            return Resultado(Status.SEM_PRECO_ENTRADA, referencia=ctx.referencia)
        if futuras[0].inicio >= fim_sessao:
            return Resultado(Status.SEM_PRECO_ENTRADA, referencia=ctx.referencia)
        k, entrada = 0, futuras[0].abertura + s * DESLIZE
    else:
        assert ordem.limite is not None
        achado = _fill_limite(
            futuras, ordem, inicio_janela, min(inicio_janela + VALIDADE_LIMITE, fim_sessao)
        )
        if isinstance(achado, Status):
            pior = (
                _pior(ordem.limite + s * DESLIZE, ordem.stop)
                if achado is Status.CENSURADO
                else None
            )
            return Resultado(achado, pior_caso_pts=pior, referencia=ctx.referencia)
        k, entrada = achado, ordem.limite + s * DESLIZE

    if ordem.distancia is not None:
        stop, alvo = entrada - s * ordem.distancia, entrada + s * ordem.distancia
    else:
        assert ordem.stop is not None and ordem.alvo is not None
        stop, alvo = ordem.stop, ordem.alvo
    posicao = Resultado(
        Status.OK,
        inicio=futuras[k].inicio,
        entrada=entrada,
        stop=stop,
        alvo=alvo,
        pior_caso_pts=_pior(entrada, stop),
        referencia=ctx.referencia,
    )

    def fecha(motivo: str, saida: Decimal, quando: datetime) -> Resultado:
        net = s * (saida - entrada) - CUSTO_IDA_VOLTA
        return replace(posicao, motivo=motivo, fim=quando, saida=saida, net_pts=net)

    if s * (entrada - stop) <= 0 or s * (alvo - entrada) <= 0:
        base_saida = futuras[k].abertura if ordem.tipo == "market" else entrada - s * DESLIZE
        return fecha("gap_na_entrada", base_saida - s * DESLIZE, futuras[k].inicio)

    limite_tempo = min(futuras[k].inicio + ctx.horizonte, fim_sessao)
    anterior: Barra | None = None
    for j in range(k, len(futuras)):
        b = futuras[j]
        if anterior is not None and b.inicio - anterior.inicio != UM_MINUTO:
            return replace(posicao, status=Status.CENSURADO, motivo="lacuna")
        anterior = b
        if b.inicio >= limite_tempo:
            return fecha("tempo", b.abertura - s * DESLIZE, b.inicio)
        so_stop = ordem.tipo == "limit" and j == k
        if s * (b.abertura - stop) <= 0 and not so_stop:
            return fecha("stop", b.abertura - s * DESLIZE, b.inicio)
        extremo_contra = b.minima if s == 1 else b.maxima
        extremo_favor = b.maxima if s == 1 else b.minima
        if s * (extremo_contra - stop) <= 0:
            return fecha("stop", stop - s * DESLIZE, b.inicio)
        if not so_stop and s * (extremo_favor - alvo) >= TICK:
            return fecha("alvo", alvo - s * DESLIZE, b.inicio)
    return replace(posicao, status=Status.CENSURADO, motivo="sem_saida")


def _fill_limite(
    futuras: Sequence[Barra], ordem: Ordem, de: datetime, ate: datetime
) -> int | Status:
    assert ordem.limite is not None
    s = _sentido(ordem.lado)
    esperado = de
    for j, b in enumerate(futuras):
        if b.inicio >= ate:
            return Status.SEM_FILL if esperado >= ate else Status.CENSURADO
        if b.inicio != esperado:
            return Status.CENSURADO
        esperado = b.inicio + UM_MINUTO
        extremo = b.minima if s == 1 else b.maxima
        if s * (ordem.limite - extremo) >= TICK:
            return j
    return Status.CENSURADO if esperado < ate else Status.SEM_FILL


def _pior(entrada: Decimal, stop: Decimal | None) -> Decimal | None:
    """Cenário condicionado (não limite) de uma posição censurada: stop + 1 tick e os custos."""
    if stop is None:
        return None
    return -(abs(entrada - stop) + DESLIZE + CUSTO_IDA_VOLTA)
