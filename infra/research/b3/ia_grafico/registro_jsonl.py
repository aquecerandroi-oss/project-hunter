"""O registro append-only da coleta: intenção antes de cada envio, resultado antes da próxima tentativa.

Três tipos de linha (Astra R3): ``inelegivel`` (instante sem janela), ``intencao`` (gravada e
debitada **antes** de enviar a tentativa *k*) e ``tentativa`` (o resultado da tentativa *k*). Na
retomada, uma intenção sem resultado conta como tentativa **consumida, de desfecho desconhecido**
— nunca dá direito a duas tentativas novas. Concluído = resposta válida, ferramenta usada, ou as
duas tentativas consumidas.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from infra.research.b3.ia_grafico.modelo import MAX_TENTATIVAS, Registro
from infra.research.b3.ia_grafico.resposta import Resposta, validar


@dataclass(frozen=True, slots=True)
class Instante:
    id: str
    t: datetime
    slot: int
    fim_sessao: datetime
    espelho: bool = False


@dataclass(frozen=True, slots=True)
class Coleta:
    instante: Instante
    grafico_sha256: str | None = None
    grafico_sha256_png: str | None = None
    referencia: Decimal | None = None
    resposta: Resposta | None = None
    registros: tuple[Registro, ...] = field(default_factory=tuple[Registro, ...])
    motivo_inelegivel: str | None = None
    tentativas_sem_desfecho: tuple[int, ...] = ()


def _base(c: Coleta) -> dict[str, Any]:
    return {
        "instante_id": c.instante.id,
        "t": c.instante.t.isoformat(),
        "slot": c.instante.slot,
        "fim_sessao": c.instante.fim_sessao.isoformat(),
        "espelho": c.instante.espelho,
        "grafico_sha256": c.grafico_sha256,
        "grafico_sha256_png": c.grafico_sha256_png,
        "referencia": None if c.referencia is None else str(c.referencia),
        "motivo_inelegivel": c.motivo_inelegivel,
    }


def _linha_tentativa(c: Coleta, reg: Registro) -> dict[str, Any]:
    linha = {"tipo": "tentativa", **_base(c), **asdict(reg)}
    linha["inicio"], linha["fim"] = reg.inicio.isoformat(), reg.fim.isoformat()
    return linha


class Diario:
    """Escreve uma linha por evento e fecha o arquivo a cada linha (sobrevive a queda do processo)."""

    def __init__(self, destino: Path) -> None:
        self.destino = destino

    def _escreve(self, linha: dict[str, Any]) -> None:
        with self.destino.open("a", encoding="utf-8") as f:
            f.write(json.dumps(linha, ensure_ascii=False, default=str) + "\n")

    def inelegivel(self, c: Coleta) -> None:
        self._escreve({"tipo": "inelegivel", **_base(c)})

    def intencao(self, c: Coleta, tentativa: int) -> None:
        agora = datetime.now(UTC).isoformat()
        self._escreve({"tipo": "intencao", **_base(c), "tentativa": tentativa, "em": agora})

    def tentativa(self, c: Coleta, reg: Registro) -> None:
        self._escreve(_linha_tentativa(c, reg))


def gravar_jsonl(coletas: Sequence[Coleta], destino: Path) -> None:
    """Grava coletas já completas (sem as intenções): uma linha por tentativa ou por inelegível."""
    diario = Diario(destino)
    for c in coletas:
        if not c.registros:
            diario.inelegivel(c)
        for reg in c.registros:
            diario.tentativa(c, reg)


@dataclass(frozen=True, slots=True)
class EstadoInstante:
    usadas: int
    concluido: bool


def _linhas(origem: Path) -> dict[str, list[dict[str, Any]]]:
    por_id: dict[str, list[dict[str, Any]]] = {}
    for texto in origem.read_text(encoding="utf-8").splitlines():
        if texto.strip():
            linha = cast(dict[str, Any], json.loads(texto))
            por_id.setdefault(str(linha["instante_id"]), []).append(linha)
    return por_id


def _estado(linhas: list[dict[str, Any]]) -> EstadoInstante:
    if any(
        x.get("tipo", "tentativa") == "inelegivel" or x.get("motivo_inelegivel") for x in linhas
    ):
        return EstadoInstante(0, True)
    tentativas = [x for x in linhas if x.get("tipo", "tentativa") == "tentativa"]
    usadas = max((int(x["tentativa"]) for x in linhas if "tentativa" in x), default=0)
    final = any(
        x.get("status") == "valida" or x.get("motivo") == "isolamento_violado" for x in tentativas
    )
    return EstadoInstante(usadas, final or usadas >= MAX_TENTATIVAS)


def estado(origem: Path) -> dict[str, EstadoInstante]:
    return {iid: _estado(linhas) for iid, linhas in _linhas(origem).items()}


def tentativas_consumidas(origem: Path) -> int:
    """Saldo do orçamento num processo novo: tentativas consumidas (intenções órfãs incluídas),
    cada tentativa contada uma vez — intenção e resultado da mesma tentativa não somam duas."""
    return sum(e.usadas for e in estado(origem).values())


def _registro(x: dict[str, Any]) -> Registro:
    campos = {k: x[k] for k in Registro.__dataclass_fields__ if k in x}
    campos["inicio"] = datetime.fromisoformat(str(x["inicio"]))
    campos["fim"] = datetime.fromisoformat(str(x["fim"]))
    return Registro(**campos)


def ler_jsonl(origem: Path) -> list[Coleta]:
    """Reconstrói as coletas (a fase 2 lê daqui): resposta revalidada da crua, tentativas e lacunas."""
    saida: list[Coleta] = []
    for iid, linhas in _linhas(origem).items():
        b = linhas[0]
        inst = Instante(
            iid,
            datetime.fromisoformat(b["t"]),
            int(b["slot"]),
            datetime.fromisoformat(b["fim_sessao"]),
            bool(b["espelho"]),
        )
        tentativas = [x for x in linhas if x.get("tipo", "tentativa") == "tentativa"]
        registros = tuple(
            _registro(x) for x in sorted(tentativas, key=lambda x: int(x["tentativa"]))
        )
        intencoes = {int(x["tentativa"]) for x in linhas if x.get("tipo") == "intencao"}
        validas = [r for r in registros if r.status == "valida"]
        ref = next((x["referencia"] for x in linhas if x.get("referencia") is not None), None)
        saida.append(
            Coleta(
                inst,
                b["grafico_sha256"],
                b["grafico_sha256_png"],
                None if ref is None else Decimal(str(ref)),
                validar(validas[0].resposta_crua) if validas else None,
                registros,
                b["motivo_inelegivel"],
                tuple(sorted(intencoes - {r.tentativa for r in registros})),
            )
        )
    return saida
