"""Validação estrita da resposta do modelo (ADR 0002: saída é dado classificado, nunca instrução).

JSON puro, chaves exatas, números finitos, geometria coerente com o lado. Qualquer desvio
levanta ``RespostaInvalida`` com um ``motivo`` nomeado — que é contado, nunca convertido em
"none". Unidades: eixo da imagem, 100·ln(p ÷ último fechamento).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, cast

_CHAVES = frozenset(
    {"side", "entry_type", "entry_y", "stop_y", "target_y", "confidence", "levels", "rationale"}
)
_CHAVES_NIVEL = frozenset({"kind", "y1", "bars_ago1", "y2", "bars_ago2", "note"})
STOP_MIN, STOP_MAX = 0.05, 3.0
ALVO_MIN, ALVO_MAX = 0.05, 5.0
LIMITE_MAX = 3.0
MAX_NIVEIS, MAX_RACIONAL, MAX_NOTA, MAX_BARS_AGO = 10, 600, 200, 119


class Lado(StrEnum):
    COMPRA = "buy"
    VENDA = "sell"
    NENHUM = "none"


class RespostaInvalida(ValueError):
    def __init__(self, motivo: str, detalhe: str = "") -> None:
        super().__init__(f"{motivo}: {detalhe}" if detalhe else motivo)
        self.motivo = motivo


@dataclass(frozen=True, slots=True)
class Nivel:
    tipo: str
    y1: float
    bars_ago1: int | None
    y2: float | None
    bars_ago2: int | None
    nota: str


@dataclass(frozen=True, slots=True)
class Resposta:
    lado: Lado
    tipo_entrada: str | None
    entrada_y: float | None
    stop_y: float | None
    alvo_y: float | None
    confianca: float
    niveis: tuple[Nivel, ...]
    racional: str

    @property
    def entrada_ref(self) -> float:
        return 0.0 if self.entrada_y is None else self.entrada_y


def _sem_duplicata(pares: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for k, v in pares:
        if k in obj:
            raise RespostaInvalida("chave_duplicada", k)
        obj[k] = v
    return obj


def _recusa_constante(nome: str) -> float:
    raise ValueError(nome)


def _numero(v: object, campo: str, *, nulo: bool = False) -> float | None:
    if v is None and nulo:
        return None
    if isinstance(v, bool) or not isinstance(v, int | float):
        raise RespostaInvalida("numero", campo)
    if not math.isfinite(v):
        raise RespostaInvalida("numero", campo)
    return float(v)


def _inteiro(v: object, campo: str) -> int | None:
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= MAX_BARS_AGO:
        raise RespostaInvalida("nivel", campo)
    return v


def _nivel(bruto: object) -> Nivel:
    if not isinstance(bruto, dict):
        raise RespostaInvalida("nivel", "chaves")
    d = cast(dict[str, Any], bruto)
    if frozenset(d) != _CHAVES_NIVEL:
        raise RespostaInvalida("nivel", "chaves")
    tipo, nota = d["kind"], d["note"]
    if tipo not in ("support", "resistance", "trendline") or not isinstance(nota, str):
        raise RespostaInvalida("nivel", "tipo ou nota")
    if len(nota) > MAX_NOTA:
        raise RespostaInvalida("nivel", "nota longa")
    try:
        y1 = _numero(d["y1"], "y1")
        y2 = _numero(d["y2"], "y2", nulo=True)
    except RespostaInvalida as e:
        raise RespostaInvalida("nivel", str(e)) from e
    b1, b2 = _inteiro(d["bars_ago1"], "bars_ago1"), _inteiro(d["bars_ago2"], "bars_ago2")
    if tipo == "trendline":
        if y2 is None or b1 is None or b2 is None or b1 == b2:
            raise RespostaInvalida("nivel", "linha precisa de dois pontos distintos")
    elif (b1, y2, b2) != (None, None, None):
        raise RespostaInvalida("nivel", "nível horizontal usa só y1")
    assert y1 is not None
    return Nivel(tipo, y1, b1, y2, b2, nota)


def validar(texto: str) -> Resposta:
    try:
        bruto: object = json.loads(
            texto, object_pairs_hook=_sem_duplicata, parse_constant=_recusa_constante
        )
    except RespostaInvalida:
        raise
    except ValueError as e:
        raise RespostaInvalida("nao_e_json", str(e)[:80]) from e
    if not isinstance(bruto, dict):
        raise RespostaInvalida("nao_e_objeto")
    d = cast(dict[str, Any], bruto)
    if frozenset(d) != _CHAVES:
        raise RespostaInvalida("chaves", ",".join(sorted(set(d) ^ _CHAVES)))
    if d["side"] not in ("buy", "sell", "none"):
        raise RespostaInvalida("lado")
    lado = Lado(d["side"])
    confianca = _numero(d["confidence"], "confidence")
    assert confianca is not None
    if not 0.0 <= confianca <= 1.0:
        raise RespostaInvalida("confianca")
    racional = d["rationale"]
    if not isinstance(racional, str) or len(racional) > MAX_RACIONAL:
        raise RespostaInvalida("racional")
    niveis_brutos = d["levels"]
    if not isinstance(niveis_brutos, list):
        raise RespostaInvalida("nivel", "lista")
    lista = cast(list[object], niveis_brutos)
    if len(lista) > MAX_NIVEIS:
        raise RespostaInvalida("nivel", "lista")
    niveis = tuple(_nivel(n) for n in lista)
    entrada = _numero(d["entry_y"], "entry_y", nulo=True)
    stop = _numero(d["stop_y"], "stop_y", nulo=True)
    alvo = _numero(d["target_y"], "target_y", nulo=True)
    tipo = d["entry_type"]
    if lado is Lado.NENHUM:
        if (tipo, entrada, stop, alvo) != (None, None, None, None):
            raise RespostaInvalida("none_com_geometria")
        return Resposta(lado, None, None, None, None, confianca, niveis, racional)
    if tipo not in ("market", "limit"):
        raise RespostaInvalida("tipo_entrada")
    if tipo == "market" and entrada is not None:
        raise RespostaInvalida("entrada_mercado_com_preco")
    if tipo == "limit":
        if entrada is None:
            raise RespostaInvalida("limite_sem_preco")
        lado_certo = entrada < 0 if lado is Lado.COMPRA else entrada > 0
        if not lado_certo or abs(entrada) > LIMITE_MAX:
            raise RespostaInvalida("limite_do_lado_errado")
    if stop is None or alvo is None:
        raise RespostaInvalida("geometria", "stop e alvo obrigatórios")
    e = 0.0 if entrada is None else entrada
    sentido = 1.0 if lado is Lado.COMPRA else -1.0
    if not (sentido * (e - stop) > 0 and sentido * (alvo - e) > 0):
        raise RespostaInvalida("geometria")
    if not STOP_MIN <= abs(e - stop) <= STOP_MAX:
        raise RespostaInvalida("distancia_stop")
    if not ALVO_MIN <= abs(alvo - e) <= ALVO_MAX:
        raise RespostaInvalida("distancia_alvo")
    return Resposta(lado, tipo, entrada, stop, alvo, confianca, niveis, racional)


def espelhar(r: Resposta) -> Resposta:
    """Desfaz (ou aplica) o espelho y → −y: lado trocado, geometria negada, níveis negados."""
    oposto = {Lado.COMPRA: Lado.VENDA, Lado.VENDA: Lado.COMPRA, Lado.NENHUM: Lado.NENHUM}

    def neg(v: float | None) -> float | None:
        return None if v is None else -v

    niveis = tuple(replace(n, y1=-n.y1, y2=neg(n.y2)) for n in r.niveis)
    return replace(
        r,
        lado=oposto[r.lado],
        entrada_y=neg(r.entrada_y),
        stop_y=neg(r.stop_y),
        alvo_y=neg(r.alvo_y),
        niveis=niveis,
    )
