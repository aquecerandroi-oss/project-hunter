"""Interface do cliente do modelo, o cliente falso (só testes) e a chamada com validação.

Política congelada (Astra R1): **primeira resposta válida em até duas tentativas** — inválida
repete uma vez, idêntica, e as duas ficam registradas; uso de qualquer ferramenta pelo agente
(shell, busca, MCP) invalida o ensaio sem repetir ("isolamento_violado"). A resposta crua nunca é
reescrita: reanalisar = reler o registro.
"""

from __future__ import annotations

import hashlib
import platform
import zlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cache
from typing import Protocol

import numpy as np

from infra.research.b3.ia_grafico.protocolo import SHA256_MODELO_PEDIDO, VERSAO_PROMPT
from infra.research.b3.ia_grafico.resposta import Resposta, RespostaInvalida, validar

MAX_TENTATIVAS = 2


@dataclass(frozen=True, slots=True)
class Pedido:
    png: bytes
    texto: str

    @property
    def sha256_png(self) -> str:
        return hashlib.sha256(self.png).hexdigest()

    @property
    def nome_imagem(self) -> str:
        """Nome opaco (16 hex + .png): nem data, nem contrato, nem instante."""
        return self.sha256_png[:16] + ".png"


@dataclass(frozen=True, slots=True)
class RespostaCrua:
    texto: str
    modelo: str
    cliente: str
    inicio: datetime
    fim: datetime
    parametros: Mapping[str, str] = field(default_factory=dict[str, str])
    tokens_entrada: int | None = None
    tokens_saida: int | None = None
    eventos_ferramenta: int = 0
    telemetria_ok: bool = True
    eventos_brutos: str = ""
    versao_cliente: str = ""


class ClienteModelo(Protocol):
    modelo: str

    def responder(self, pedido: Pedido) -> RespostaCrua: ...


class ClienteFalso:
    """Só para testes: ``politica`` vê o pedido (imagem + texto) e devolve o texto da resposta."""

    modelo = "falso/teste"

    def __init__(
        self,
        politica: Callable[[Pedido], str],
        *,
        relogio: Callable[[], datetime],
        eventos_ferramenta: int = 0,
        telemetria_ok: bool = True,
    ) -> None:
        self._politica, self._relogio, self._eventos = politica, relogio, eventos_ferramenta
        self._telemetria_ok = telemetria_ok

    def responder(self, pedido: Pedido) -> RespostaCrua:
        inicio = self._relogio()
        texto = self._politica(pedido)
        return RespostaCrua(
            texto=texto,
            modelo="falso/teste",
            cliente="falso",
            inicio=inicio,
            fim=self._relogio(),
            eventos_ferramenta=self._eventos,
            telemetria_ok=self._telemetria_ok,
        )


@cache
def ambiente() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "zlib": zlib.ZLIB_RUNTIME_VERSION,
        "sistema": platform.system(),
    }


@dataclass(frozen=True, slots=True)
class Registro:
    tentativa: int
    status: str
    motivo: str | None
    resposta_crua: str
    modelo: str
    cliente: str
    parametros: Mapping[str, str]
    inicio: datetime
    fim: datetime
    tokens_entrada: int | None
    tokens_saida: int | None
    eventos_ferramenta: int
    sha256_png: str
    sha256_pedido: str
    telemetria_ok: bool = True
    eventos_brutos: str = ""
    versao_cliente: str = ""
    versao_prompt: str = VERSAO_PROMPT
    sha256_modelo_pedido: str = SHA256_MODELO_PEDIDO
    ambiente: Mapping[str, str] = field(default_factory=lambda: dict(ambiente()))


def _falha_do_cliente(cliente: ClienteModelo, erro: Exception, inicio: datetime) -> RespostaCrua:
    """Timeout ou erro de transporte vira tentativa registrada — nunca some, nunca é reenviada calada."""
    return RespostaCrua(
        texto=f"{type(erro).__name__}: {erro}"[:300],
        modelo=cliente.modelo,
        cliente="erro",
        inicio=inicio,
        fim=datetime.now(UTC),
        telemetria_ok=False,
    )


def chamar(
    cliente: ClienteModelo,
    pedido: Pedido,
    *,
    ja_usadas: int = 0,
    antes_de_enviar: Callable[[int], None] | None = None,
    ao_registrar: Callable[[Registro], None] | None = None,
) -> tuple[Resposta | None, list[Registro]]:
    """Primeira resposta válida em até duas tentativas; ferramenta usada encerra sem repetir.

    Motivos de tentativa inválida: ``erro_cliente`` (exceção do cliente), ``telemetria_invalida``
    (saída não zero, evento ilegível ou protocolo incompleto: isolamento não comprovado),
    ``isolamento_violado`` e os de ``validar``. ``antes_de_enviar(k)`` roda antes do envio da
    tentativa *k* (intenção + débito) e ``ao_registrar`` antes da próxima (Astra R3); ``ja_usadas``
    vem da retomada e nunca devolve tentativas.
    """
    registros: list[Registro] = []
    sha_pedido = hashlib.sha256(pedido.texto.encode()).hexdigest()
    for tentativa in range(ja_usadas + 1, MAX_TENTATIVAS + 1):
        if antes_de_enviar is not None:
            antes_de_enviar(tentativa)
        inicio = datetime.now(UTC)
        erro_cliente = False
        try:
            crua = cliente.responder(pedido)
        except Exception as e:
            crua, erro_cliente = _falha_do_cliente(cliente, e, inicio), True
        resposta: Resposta | None = None
        motivo: str | None = None
        if erro_cliente:
            motivo = "erro_cliente"
        elif crua.eventos_ferramenta:
            motivo = "isolamento_violado"
        elif not crua.telemetria_ok:
            motivo = "telemetria_invalida"
        else:
            try:
                resposta = validar(crua.texto)
            except RespostaInvalida as e:
                motivo = e.motivo
        registros.append(
            Registro(
                tentativa=tentativa,
                status="valida" if resposta is not None else "invalida",
                motivo=motivo,
                resposta_crua=crua.texto,
                modelo=crua.modelo,
                cliente=crua.cliente,
                parametros=dict(crua.parametros),
                inicio=crua.inicio,
                fim=crua.fim,
                tokens_entrada=crua.tokens_entrada,
                tokens_saida=crua.tokens_saida,
                eventos_ferramenta=crua.eventos_ferramenta,
                sha256_png=pedido.sha256_png,
                sha256_pedido=sha_pedido,
                telemetria_ok=crua.telemetria_ok,
                eventos_brutos=crua.eventos_brutos,
                versao_cliente=crua.versao_cliente,
            )
        )
        if ao_registrar is not None:
            ao_registrar(registros[-1])
        if resposta is not None or motivo == "isolamento_violado":
            return resposta, registros
    return None, registros
