"""Instante → janela → imagem → cliente → validação (fase 1) e → simulação (fase 2).

As fases são separadas de propósito (Astra R1): a **coleta** só desenha a janela causal e
guarda as respostas; a **avaliação** — a única que lê barras depois de *t* — roda depois, sobre o
que já foi gravado. Nenhuma resposta é pedida de novo depois que um retorno foi visto.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from infra.research.b3.ia_grafico.barras import (
    BRT,
    BaldeIncompletoError,
    Barra,
    data_pregao,
    dobrar,
    janela_causal,
)
from infra.research.b3.ia_grafico.estatistica import Celula
from infra.research.b3.ia_grafico.linhas_de_base import (
    distancia_direcional,
    lado_media_movel,
    ordem_da_resposta,
)
from infra.research.b3.ia_grafico.modelo import (
    MAX_TENTATIVAS,
    ClienteModelo,
    Pedido,
    Registro,
    chamar,
)
from infra.research.b3.ia_grafico.protocolo import HORIZONTE, INSTANTES_APOS_ABERTURA, pedido
from infra.research.b3.ia_grafico.registro_jsonl import (
    Coleta,
    Diario,
    Instante,
    estado,
    gravar_jsonl,
    ler_jsonl,
)
from infra.research.b3.ia_grafico.render import MINUTOS, JanelaCurtaError, renderizar
from infra.research.b3.ia_grafico.resposta import Lado, espelhar
from infra.research.b3.ia_grafico.simulador import (
    CUSTO_IDA_VOLTA,
    DESLIZE,
    Contexto,
    Ordem,
    Status,
    simular,
)

PREGOES_DE_CONTEXTO = 3

__all__ = ["Coleta", "Instante", "gravar_jsonl", "ler_jsonl"]


def instantes_do_pregao(d: date, *, abertura: datetime, fim: datetime) -> list[Instante]:
    """Grade fixa O+30 … O+360; O e C (fim) vêm da grade histórica da data."""
    return [
        Instante(f"{d.isoformat()}-{k:02d}", abertura + delta, k, fim)
        for k, delta in enumerate(INSTANTES_APOS_ABERTURA)
    ]


class _Indice:
    """Barras por data de pregão (BRT), para não varrer o histórico inteiro a cada instante."""

    def __init__(self, barras: Sequence[Barra]) -> None:
        self._por_dia: dict[object, list[Barra]] = {}
        for b in barras:
            self._por_dia.setdefault(data_pregao(b.inicio), []).append(b)
        self._dias = sorted(self._por_dia, key=str)

    def ate(self, t: datetime, *, contexto: int) -> list[Barra]:
        dia = data_pregao(t)
        anteriores = [d for d in self._dias if str(d) <= str(dia)][-(contexto + 1) :]
        return [b for d in anteriores for b in self._por_dia[d]]

    def do_dia(self, t: datetime) -> list[Barra]:
        return self._por_dia.get(data_pregao(t), [])


class Orcamento:
    """Teto de **tentativas** (chamadas), cumulativo entre lotes (Astra R2).

    Nenhum instante começa sem folga para as duas tentativas; por isso um teto de N tentativas pode
    parar antes de N ÷ 1 instantes — a meta de instantes e o orçamento de tentativas são coisas
    diferentes. Entre processos, o saldo se reconstrói contando as linhas do JSONL.
    """

    def __init__(self, maximo: int, gastas: int = 0) -> None:
        self.maximo, self.gastas = maximo, gastas

    def cabe(self, tentativas: int) -> bool:
        return self.gastas + tentativas <= self.maximo


class OrcamentoEsgotado(RuntimeError):
    """O teto pararia no meio de um instante: para antes, com o que já foi coletado."""

    def __init__(self, coletas: list[Coleta]) -> None:
        super().__init__(f"orçamento de tentativas esgotado depois de {len(coletas)} instantes")
        self.coletas = coletas


def coletar(
    barras: Sequence[Barra],
    instantes: Sequence[Instante],
    cliente: ClienteModelo,
    *,
    orcamento: Orcamento | None = None,
    destino: Path | None = None,
) -> list[Coleta]:
    """Fase 1. Com ``destino``: intenção gravada e debitada antes de cada envio, resultado gravado
    antes da próxima tentativa; a retomada pula concluídos e continua da tentativa seguinte."""
    indice = _Indice(barras)
    diario = Diario(destino) if destino is not None else None
    estados = estado(destino) if destino is not None and destino.exists() else {}
    saida: list[Coleta] = []
    for i in instantes:
        anterior = estados.get(i.id)
        if anterior is not None and anterior.concluido:
            continue
        usadas = 0 if anterior is None else anterior.usadas
        try:
            g = renderizar(indice.ate(i.t, contexto=PREGOES_DE_CONTEXTO), i.t, espelho=i.espelho)
        except (BaldeIncompletoError, JanelaCurtaError) as e:
            coleta = Coleta(i, motivo_inelegivel=f"{type(e).__name__}: {e}")
            if diario is not None:
                diario.inelegivel(coleta)
            saida.append(coleta)
            continue
        if orcamento is not None and not orcamento.cabe(MAX_TENTATIVAS - usadas):
            raise OrcamentoEsgotado(saida)
        parcial = Coleta(i, g.sha256_pixels, g.sha256_png, g.referencia)

        def antes(k: int, parcial: Coleta = parcial) -> None:
            if orcamento is not None:
                orcamento.gastas += 1
            if diario is not None:
                diario.intencao(parcial, k)

        def registra(reg: Registro, parcial: Coleta = parcial) -> None:
            if diario is not None:
                diario.tentativa(parcial, reg)

        hora = i.t.astimezone(BRT).strftime("%H:%M")
        resposta, registros = chamar(
            cliente,
            Pedido(g.png, pedido(hora)),
            ja_usadas=usadas,
            antes_de_enviar=antes,
            ao_registrar=registra,
        )
        saida.append(replace(parcial, resposta=resposta, registros=tuple(registros)))
    return saida


@dataclass(frozen=True, slots=True)
class Avaliacao:
    celulas: list[Celula]
    completo_bp: list[float]
    n_sem_preco_entrada: int
    n_censuradas_completo: int
    n_sem_fill: int


def _bp(pts: Decimal | None, ref: Decimal) -> float:
    if pts is None:
        raise ValueError("pontos ausentes")
    return float(pts / ref * 10_000)


def avaliar(
    barras: Sequence[Barra], coletas: Sequence[Coleta], *, horizonte: timedelta = HORIZONTE
) -> Avaliacao:
    indice = _Indice(barras)
    celulas: list[Celula] = []
    completo: list[float] = []
    sem_preco = censuradas = sem_fill = 0
    for c in coletas:
        if c.motivo_inelegivel or c.referencia is None:
            continue
        i, ref = c.instante, c.referencia
        passado = janela_causal(indice.ate(i.t, contexto=PREGOES_DE_CONTEXTO), i.t)
        cinco = dobrar(passado, i.t, minutos=MINUTOS)
        dia = indice.do_dia(i.t)
        ctx = Contexto(t=i.t, fim_sessao=i.fim_sessao, referencia=ref, horizonte=horizonte)
        dist = distancia_direcional(cinco)
        compra = simular(dia, Ordem(Lado.COMPRA, "market", distancia=dist), ctx)
        venda = simular(dia, Ordem(Lado.VENDA, "market", distancia=dist), ctx)
        if Status.SEM_PRECO_ENTRADA in (compra.status, venda.status):
            sem_preco += 1
            continue
        resposta = espelhar(c.resposta) if c.resposta is not None and i.espelho else c.resposta
        pior = _bp(-(dist + DESLIZE + CUSTO_IDA_VOLTA), ref)
        melhor = _bp(dist - DESLIZE - CUSTO_IDA_VOLTA, ref)
        celulas.append(
            Celula(
                dia=i.t.astimezone(BRT).date(),
                slot=i.slot,
                lado_ia=resposta.lado if resposta is not None else None,
                compra_bp=compra.net_bp,
                venda_bp=venda.net_bp,
                compra_pior_bp=pior,
                venda_pior_bp=pior,
                compra_melhor_bp=melhor,
                venda_melhor_bp=melhor,
                lado_mm=lado_media_movel(cinco),
            )
        )
        if resposta is None:
            continue
        if resposta.lado is Lado.NENHUM:
            completo.append(0.0)
            continue
        r = simular(dia, ordem_da_resposta(resposta, ref), ctx)
        if r.status is Status.OK:
            completo.append(_bp(r.net_pts, ref))
        elif r.status is Status.SEM_FILL:
            sem_fill += 1
            completo.append(0.0)
        elif r.status is Status.CENSURADO:
            censuradas += 1
            completo.append(_bp(r.pior_caso_pts, ref))
        else:
            sem_preco += 1
    return Avaliacao(celulas, completo, sem_preco, censuradas, sem_fill)
