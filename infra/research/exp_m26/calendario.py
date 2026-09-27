"""Seed → T0 → corte → leitura (§4). Puro: o instante `agora` é dado, nunca lido.

- **T0** = seed + 48 h (piloto técnico fora da inferência).
- **Corte**: a 1.ª meia-noite UTC `M ≥ T0 + 7 d` em que C tem ≥ 150 `true` e ≥ 450 `false`
  inscritas com `evaluated_at ∈ [T0, M)`; no máximo `M_max` = 1.ª meia-noite `≥ T0 + 21 d`.
  Cada candidata só olha o que chegou antes dela.
- **Parada pela guarda** (§6.8; J: aposentadoria de qualquer braço antes do corte) encerra
  a inscrição no instante da parada.
- **Leitura** = corte + 2 h, fixa. Pedir antes disso levanta `LeituraAntecipada`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from infra.research.exp_m26.constantes import (
    DIAS_MAXIMOS,
    DIAS_MINIMOS,
    LEITURA_APOS_CORTE,
    META_FALSE,
    META_TRUE,
    PILOTO,
)


class LeituraAntecipada(RuntimeError):
    """O instante da leitura ainda não chegou (ou o corte ainda não se decidiu)."""


@dataclass(frozen=True)
class Corte:
    instante: datetime
    motivo: str
    """`metas` | `dia_21` | `parada_guarda`."""
    leitura: datetime


def t0_de(seed: datetime) -> datetime:
    return seed + PILOTO


def meia_noite(t: datetime) -> datetime:
    """A 1.ª meia-noite UTC maior ou igual a `t`."""
    u = t.astimezone(UTC)
    m = datetime(u.year, u.month, u.day, tzinfo=UTC)
    return m if m == u else m + timedelta(days=1)


def corte(
    t0: datetime,
    inscricoes: Sequence[tuple[datetime, str]],
    *,
    parada: datetime | None,
    agora: datetime,
) -> Corte:
    """`inscricoes` = `(evaluated_at, classe)` das elegíveis de C (não E, fora do piloto)."""
    m = meia_noite(t0 + timedelta(days=DIAS_MINIMOS))
    fim = meia_noite(t0 + timedelta(days=DIAS_MAXIMOS))
    while True:
        if parada is not None and parada < m:
            return _fechar(parada, "parada_guarda", agora)
        if m + LEITURA_APOS_CORTE > agora:
            raise LeituraAntecipada(f"o corte candidato {m.isoformat()} só se lê depois de {agora}")
        nt = sum(1 for t, k in inscricoes if t0 <= t < m and k == "true")
        nf = sum(1 for t, k in inscricoes if t0 <= t < m and k == "false")
        if nt >= META_TRUE and nf >= META_FALSE:
            return _fechar(m, "metas", agora)
        if m >= fim:
            return _fechar(m, "dia_21", agora)
        m += timedelta(days=1)


def _fechar(instante: datetime, motivo: str, agora: datetime) -> Corte:
    leitura = instante + LEITURA_APOS_CORTE
    if agora < leitura:
        raise LeituraAntecipada(f"leitura em {leitura.isoformat()}, agora é {agora.isoformat()}")
    return Corte(instante, motivo, leitura)
