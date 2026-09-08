"""Jitter de parâmetros — como uma irmã nasce (`docs/plans/REPLICATION.md` §4.2).

Cada parâmetro **numérico** do conjunto congelado do pai recebe um fator
independente ``U(1 − pct, 1 + pct)`` de um RNG semeado. O que sai é um conjunto
que ainda **valida contra o mesmo schema congelado** — é essa a parte difícil, e
é por isso que este módulo lê o schema em vez de mexer nos números às cegas:

- os números do ``params_format = 1`` viajam como **string normalizada**
  (``canonical.py``), então ``"20"`` é o inteiro 20 e ``"1.5"`` é o decimal 1,5;
  a representação de entrada é preservada na saída;
- ``pattern`` do schema (``^-?[0-9]+(\\.[0-9]+)?$``) não aceita expoente, então
  a saída é sempre forma posicional sem zeros à direita;
- ``minimum``/``maximum`` são respeitados por clamp quando o schema os declara
  (os schemas de hoje não declaram — a limitação está escrita em
  ``hunter_core.strategies.schema``);
- **timeframes, enums, strings e booleanos passam intactos**: trocar
  ``atr_timeframe`` não é jitter, é outra estratégia;
- **zero continua zero**: um limiar declarado como ausência de limiar
  (``return_min = 0``) não vira ``0,0000001`` por causa de um fator multiplicativo;
- um inteiro positivo nunca vira 0 ou negativo (piso :data:`MIN_INTEGER`):
  janela zero não é uma variante, é um erro.

Determinismo: os parâmetros são percorridos em **ordem alfabética** e o gerador é
um ``PCG64`` explícito. Mesma semente + mesmo conjunto de entrada = mesmas irmãs,
em qualquer máquina — o que torna a semente registrada uma prova reexecutável.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import numpy as np

__all__ = [
    "DECIMAL_PLACES_EXTRA",
    "DECIMAL_PLACES_MIN",
    "JITTER_PCT",
    "MIN_INTEGER",
    "JitterChange",
    "JitterResult",
    "jitter_parameters",
]

JITTER_PCT = Decimal("0.15")
"""``JITTER_PCT`` do protocolo: ±15 % uniforme, independente por parâmetro."""

MIN_INTEGER = 1
"""``JITTER_MIN_INTEIRO``: piso de um inteiro positivo depois do arredondamento."""

DECIMAL_PLACES_EXTRA = 2
"""``JITTER_CASAS_EXTRA``: casas adicionais sobre as do valor original."""

DECIMAL_PLACES_MIN = 4
"""``JITTER_CASAS_MIN``: piso de casas decimais, para o jitter não ser engolido
pelo arredondamento (``3`` com ±15 % precisa de mais que zero casas)."""

_NUMERIC_STRING = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")


@dataclass(frozen=True, slots=True)
class JitterChange:
    """Um parâmetro deslocado: o antes, o depois e o fator que os liga."""

    name: str
    original: str
    jittered: str
    factor: str


@dataclass(frozen=True, slots=True)
class JitterResult:
    """O conjunto derivado, mais o rastro de como ele foi derivado."""

    parameters: dict[str, Any]
    changes: tuple[JitterChange, ...]
    untouched: tuple[str, ...]
    seed: int
    pct: Decimal

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "pct": str(self.pct),
            "untouched": list(self.untouched),
            "changes": [
                {
                    "name": change.name,
                    "original": change.original,
                    "jittered": change.jittered,
                    "factor": change.factor,
                }
                for change in self.changes
            ],
        }


def _rule_types(rule: Mapping[str, Any]) -> list[str]:
    declared = rule.get("type")
    if declared is None:
        return []
    return [declared] if isinstance(declared, str) else list(declared)


def _numeric_kind(rule: Mapping[str, Any], value: object) -> str | None:
    """``"integer"``, ``"number"`` ou ``None`` (não é para deslocar).

    O schema manda; o valor só confirma. Um ``bool`` é ``int`` em Python e nunca
    é numérico aqui — ``{"enabled": true}`` e ``{"enabled": 1}`` seriam o mesmo
    experimento, e ``canonical.py`` já se recusa a confundi-los.
    """
    if isinstance(value, bool) or value is None:
        return None
    types = _rule_types(rule)
    if isinstance(value, str):
        if not _NUMERIC_STRING.fullmatch(value):
            return None
    elif not isinstance(value, (int, float, Decimal)):
        return None
    if "integer" in types and "number" not in types:
        return "integer"
    if "number" in types:
        return "number"
    if not types:  # sem schema declarado: só o próprio valor decide
        return "integer" if isinstance(value, int) else "number"
    return None


def _places(value: Decimal) -> int:
    exponent = value.as_tuple().exponent
    original = -int(exponent) if isinstance(exponent, int) and exponent < 0 else 0
    return max(original + DECIMAL_PLACES_EXTRA, DECIMAL_PLACES_MIN)


def _format(value: Decimal) -> str:
    """Forma posicional canônica: sem expoente, sem zeros à direita, sem ``-0``."""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _clamp(value: Decimal, rule: Mapping[str, Any]) -> Decimal:
    minimum, maximum = rule.get("minimum"), rule.get("maximum")
    if minimum is not None:
        value = max(value, Decimal(str(minimum)))
    if maximum is not None:
        value = min(value, Decimal(str(maximum)))
    return value


def _shift(value: Decimal, factor: Decimal, kind: str, rule: Mapping[str, Any]) -> Decimal:
    if value == 0:
        return value
    moved = value * factor
    if kind == "integer":
        moved = moved.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        if value > 0:
            moved = max(moved, Decimal(MIN_INTEGER))
        elif value < 0:
            moved = min(moved, Decimal(-MIN_INTEGER))
    else:
        moved = moved.quantize(Decimal(1).scaleb(-_places(value)), rounding=ROUND_HALF_UP)
    return _clamp(moved, rule)


def _restore(moved: Decimal, original: object, kind: str) -> Any:
    """Devolve na mesma representação em que entrou (string canônica ou tipada)."""
    if isinstance(original, str):
        return _format(moved)
    if kind == "integer":
        return int(moved)
    return moved


def jitter_parameters(
    params: Mapping[str, Any],
    schema: Mapping[str, Any],
    *,
    seed: int,
    pct: Decimal = JITTER_PCT,
    frozen: Sequence[str] = (),
) -> JitterResult:
    """Um conjunto de parâmetros irmão, derivado de ``params`` com semente ``seed``.

    ``frozen`` permite congelar nomes explicitamente (nenhum, por padrão: o
    protocolo desloca **todos** os numéricos, inclusive os de custo assumido —
    ver REPLICATION.md §4.2, que declara essa leitura).
    """
    if pct <= 0 or pct >= 1:
        raise ValueError(f"pct fora de (0, 1): {pct}")
    properties: Mapping[str, Any] = schema.get("properties") or {}
    rng = np.random.Generator(np.random.PCG64(seed))
    low, high = float(1 - pct), float(1 + pct)
    derived: dict[str, Any] = dict(params)
    changes: list[JitterChange] = []
    untouched: list[str] = []
    for name in sorted(params):
        value = params[name]
        rule: Mapping[str, Any] = properties.get(name) or {}
        kind = None if name in frozen else _numeric_kind(rule, value)
        if kind is None:
            untouched.append(name)
            continue
        # Um sorteio por parâmetro, sempre, mesmo que o valor seja zero: o fluxo
        # do RNG não pode depender do conteúdo, senão a semente deixa de
        # descrever a derivação.
        factor = Decimal(repr(float(rng.uniform(low, high))))
        current = Decimal(str(value))
        moved = _shift(current, factor, kind, rule)
        derived[name] = _restore(moved, value, kind)
        if moved == current:
            untouched.append(name)
            continue
        changes.append(
            JitterChange(
                name=name,
                original=_format(current),
                jittered=_format(moved),
                factor=str(factor.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)),
            )
        )
    return JitterResult(
        parameters=derived,
        changes=tuple(changes),
        untouched=tuple(untouched),
        seed=seed,
        pct=pct,
    )
