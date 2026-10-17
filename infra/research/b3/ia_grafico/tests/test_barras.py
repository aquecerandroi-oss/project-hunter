"""Barras de 1 min, janela causal e dobra em 5 min — com valores calculados à mão."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from infra.research.b3.ia_grafico.barras import (
    AntecipacaoError,
    BaldeIncompletoError,
    Barra,
    dobrar,
    exigir_causal,
    janela_causal,
)
from infra.research.b3.ia_grafico.tests.fabrica import UM_MIN, barra, brt

D = date(2026, 3, 9)


def test_barra_recusa_instante_ingenuo_e_ohlc_incoerente() -> None:
    with pytest.raises(ValueError, match="aware"):
        Barra(
            inicio=datetime(2026, 3, 9, 13, 0),  # noqa: DTZ001 — o teste é a recusa
            duracao=UM_MIN,
            abertura=Decimal(1),
            maxima=Decimal(1),
            minima=Decimal(1),
            fechamento=Decimal(1),
            volume=Decimal(0),
        )
    with pytest.raises(ValueError, match="OHLC"):
        barra(brt(D, 10, 0), 100, 99, 95, 98)


def test_janela_causal_so_barras_finais_com_fim_ate_t() -> None:
    t = brt(D, 10, 3)
    b0 = barra(brt(D, 10, 0), 100, 105, 95, 100)
    b1 = barra(brt(D, 10, 1), 100, 105, 95, 105)
    nao_final = barra(brt(D, 10, 2), 105, 110, 100, 110, final=False)
    no_limite = barra(brt(D, 10, 3) - UM_MIN + timedelta(0), 110, 110, 105, 105, final=True)
    atravessa = barra(brt(D, 10, 3) - timedelta(seconds=30), 1, 1, 1, 1)
    futura = barra(brt(D, 10, 3), 105, 200, 100, 200)
    janela = janela_causal([futura, atravessa, b1, nao_final, no_limite, b0], t)
    # `no_limite` (10:02–10:03) termina exatamente em t: entra; a parcial e a futura não.
    assert janela == (b0, b1, no_limite)


def test_exigir_causal_recusa_barra_depois_de_t_ou_nao_final() -> None:
    t = brt(D, 10, 2)
    ok = barra(brt(D, 10, 0), 100, 105, 95, 100)
    with pytest.raises(AntecipacaoError, match="depois de t"):
        exigir_causal([ok, barra(brt(D, 10, 2), 1, 1, 1, 1)], t)
    with pytest.raises(AntecipacaoError, match="não final"):
        exigir_causal([replace(ok, final=False)], t)
    exigir_causal([ok], t)


def test_dobra_em_5_min_valores_conhecidos_e_descarta_balde_incompleto() -> None:
    um = [
        barra(brt(D, 10, 0), 100, 110, 95, 105, volume=1),
        barra(brt(D, 10, 1), 105, 120, 100, 115, volume=2),
        barra(brt(D, 10, 2), 115, 118, 110, 115, volume=0),
        barra(brt(D, 10, 3), 115, 116, 90, 95, volume=3),
        barra(brt(D, 10, 4), 95, 99, 92, 97, volume=4),
        barra(brt(D, 10, 5), 97, 98, 94, 96, volume=5),  # balde 10:05 só até 10:06
    ]
    t = brt(D, 10, 6)
    cinco = dobrar(janela_causal(um, t), t, minutos=5)
    assert len(cinco) == 1  # o balde 10:05–10:10 termina depois de t: nunca entra
    b = cinco[0]
    assert (b.inicio, b.duracao) == (brt(D, 10, 0), timedelta(minutes=5))
    assert (b.abertura, b.maxima, b.minima, b.fechamento, b.volume) == (
        Decimal(100),
        Decimal(120),
        Decimal(90),
        Decimal(97),
        Decimal(10),
    )


def test_dobra_recusa_minutos_que_nao_dividem_a_hora() -> None:
    with pytest.raises(ValueError, match="dividir"):
        dobrar([], datetime(2026, 3, 9, 13, tzinfo=UTC), minutos=7)


def test_barra_recusa_float_nan_e_infinito_em_runtime() -> None:
    with pytest.raises(TypeError, match="Decimal"):
        Barra(
            inicio=brt(D, 10, 0),
            duracao=UM_MIN,
            abertura=100.0,  # type: ignore[arg-type] — o teste é a recusa em runtime
            maxima=Decimal(100),
            minima=Decimal(100),
            fechamento=Decimal(100),
            volume=Decimal(0),
        )
    with pytest.raises(ValueError, match="finito"):
        barra(brt(D, 10, 0), 100, 100, 100, 100).__class__(
            inicio=brt(D, 10, 0),
            duracao=UM_MIN,
            abertura=Decimal("NaN"),
            maxima=Decimal(100),
            minima=Decimal(100),
            fechamento=Decimal(100),
            volume=Decimal(0),
        )


def test_dobra_recusa_balde_incompleto_buraco_intradiario_e_duplicata() -> None:
    """Minuto ausente não prova ausência de negócio (Astra R1): a janela fica indisponível."""
    cheio = [barra(brt(D, 10, m), 100, 105, 95, 100) for m in range(10)]
    t = brt(D, 10, 10)
    assert len(dobrar(cheio, t, minutos=5)) == 2

    sem_um = [b for b in cheio if b.inicio != brt(D, 10, 7)]
    with pytest.raises(BaldeIncompletoError, match="4 de 5"):
        dobrar(sem_um, t, minutos=5)

    buraco = [b for b in cheio if b.inicio < brt(D, 10, 5)] + [
        barra(brt(D, 10, m), 100, 105, 95, 100) for m in range(15, 20)
    ]
    with pytest.raises(BaldeIncompletoError, match="buraco"):
        dobrar(buraco, brt(D, 10, 20), minutos=5)

    with pytest.raises(ValueError, match="duplicada"):
        dobrar([*cheio, cheio[3]], t, minutos=5)


def test_troca_de_pregao_nao_e_buraco() -> None:
    d2 = date(2026, 3, 10)
    um = [barra(brt(D, 17, 55 + m), 100, 105, 95, 100) for m in range(5)]
    dois = [barra(brt(d2, 9, m), 100, 105, 95, 100) for m in range(5)]
    assert len(dobrar(um + dois, brt(d2, 9, 5), minutos=5)) == 2


def test_dobra_recusa_minuto_desalinhado() -> None:
    """Astra R2: cinco carimbos distintos não provam cinco minutos alinhados."""
    um = [barra(brt(D, 10, m), 100, 105, 95, 100) for m in range(4)]
    um.append(barra(brt(D, 10, 3) + timedelta(seconds=30), 100, 105, 95, 100))
    with pytest.raises(ValueError, match="alinhad"):
        dobrar(um, brt(D, 10, 5), minutos=5)
