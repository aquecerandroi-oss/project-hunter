"""``hunter_indicators.breadth`` — a amplitude do universo, com valores esperados.

T3.77 / H-P8. Universo sintético, números conferidos à mão: o minuto do
KB-0083 (194 de 200 caindo -> 0,9700), a recusa por cobertura, as duas
fronteiras da comparação (empate não é queda) e a prova de não antecipação —
uma vela **um minuto atrasada demais** não pode entrar na leitura, e mudar essa
vela não pode mudar o número.

Roda: ``uv run pytest packages/indicators/tests/unit/test_breadth_series.py -q``
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_indicators.breadth import (
    MIN_COVERAGE,
    REASON_EMPTY_UNIVERSE,
    REASON_INSUFFICIENT_COVERAGE,
    WINDOW_MINUTES,
    compute_breadth,
    window_open_times,
)

MINUTE = timedelta(minutes=1)
CUT = datetime(2026, 9, 9, 22, 8, tzinfo=UTC)
"""O minuto do KB-0083: 22:08Z de 09/09, quando 194 de 200 perpétuas caíram."""


def series(*closes: str, start: datetime = CUT - 6 * MINUTE) -> dict[datetime, Decimal]:
    """``{open_time: close}`` a partir de ``start``, um minuto por valor."""
    return {start + index * MINUTE: Decimal(value) for index, value in enumerate(closes)}


def flat(value: str = "100") -> dict[datetime, Decimal]:
    return series(*([value] * (WINDOW_MINUTES + 1)))


def falling(first: str = "100", last: str = "99") -> dict[datetime, Decimal]:
    return series(first, "100", "100", "100", "100", last)


def rising(first: str = "100", last: str = "101") -> dict[datetime, Decimal]:
    return series(first, "100", "100", "100", "100", last)


class TestOsMinutosQueEntram:
    def test_a_janela_pede_seis_velas_e_a_ultima_fecha_no_corte(self) -> None:
        """Seis ``open_time``, de ``corte-6min`` a ``corte-1min``: a vela mais
        nova admitida é a que **fecha** exatamente no corte."""
        needed = window_open_times(CUT)
        assert len(needed) == WINDOW_MINUTES + 1
        assert needed[0] == CUT - 6 * MINUTE
        assert needed[-1] == CUT - MINUTE
        assert CUT not in needed

    def test_uma_janela_menor_que_um_minuto_nao_existe(self) -> None:
        with pytest.raises(ValueError, match="at least 1"):
            window_open_times(CUT, 0)


class TestAAritmetica:
    def test_o_minuto_do_kb_0083_da_exatamente_zero_ponto_nove_sete(self) -> None:
        """194 de 200 caindo, universo de 200 com cobertura total: 0,9700."""
        universe = {f"m{i}": (falling() if i < 194 else rising()) for i in range(200)}
        reading = compute_breadth(universe, end_time=CUT, universe_size=200)
        assert reading.covered == 200
        assert reading.falling == 194
        assert reading.value == Decimal("0.9700")
        assert reading.coverage == Decimal("1.0000")
        assert reading.usable is True
        assert reading.reason is None

    def test_empate_nao_e_queda(self) -> None:
        """``<`` estrito: um mercado que fecha no mesmo preço não caiu."""
        universe = {"a": flat(), "b": falling()}
        reading = compute_breadth(universe, end_time=CUT, universe_size=2)
        assert (reading.falling, reading.covered) == (1, 2)
        assert reading.value == Decimal("0.5000")

    def test_so_o_primeiro_e_o_ultimo_fechamento_decidem(self) -> None:
        """Uma queda funda no meio da janela que volta ao ponto de partida **não**
        é queda: a leitura é sobre cinco minutos, não sobre o caminho."""
        universe = {"a": series("100", "90", "80", "70", "60", "100")}
        reading = compute_breadth(universe, end_time=CUT, universe_size=1)
        assert reading.falling == 0

    def test_o_valor_e_fracao_dos_cobertos_nunca_do_universo(self) -> None:
        """Nove de dez respondem, oito caem: 8/9, não 8/10 — a resposta é sobre
        quem foi visto, e a cobertura fica na própria linha para quem auditar."""
        universe: dict[str, dict[datetime, Decimal]] = {
            f"m{i}": (falling() if i < 8 else rising()) for i in range(9)
        }
        universe["m9"] = series("100", "100")
        reading = compute_breadth(universe, end_time=CUT, universe_size=10)
        assert (reading.covered, reading.falling) == (9, 8)
        assert reading.value == Decimal("0.8889")
        assert reading.coverage == Decimal("0.9000")


class TestCobertura:
    def test_abaixo_do_piso_a_resposta_e_ausencia_e_nao_um_numero(self) -> None:
        """Seis mercados de dez, cinco caindo: 0,83 seria "o universo desabou" e a
        verdade é "não deu para olhar"."""
        universe = {f"m{i}": (falling() if i < 5 else rising()) for i in range(6)}
        reading = compute_breadth(universe, end_time=CUT, universe_size=10)
        assert reading.coverage == Decimal("0.6000")
        assert reading.value is None
        assert reading.usable is False
        assert reading.reason == REASON_INSUFFICIENT_COVERAGE

    def test_exatamente_no_piso_a_leitura_vale(self) -> None:
        """O piso é ``>=``: oito de dez passa, e é a fronteira que a T3.77 fixa."""
        universe = {f"m{i}": (falling() if i < 4 else rising()) for i in range(8)}
        reading = compute_breadth(universe, end_time=CUT, universe_size=10)
        assert reading.coverage == MIN_COVERAGE.quantize(Decimal("0.0001"))
        assert reading.usable is True
        assert reading.value == Decimal("0.5000")

    def test_universo_vazio_tem_o_proprio_motivo(self) -> None:
        reading = compute_breadth({}, end_time=CUT, universe_size=0)
        assert (reading.value, reading.reason) == (None, REASON_EMPTY_UNIVERSE)

    def test_um_mercado_com_cinco_das_seis_velas_nao_e_contado(self) -> None:
        """ "Completa ou não existe": um buraco no meio da janela deixa um
        fechamento de antes e um de depois do buraco, e chamar isso de movimento
        de cinco minutos é afirmar minutos que ninguém observou."""
        holed = falling()
        del holed[CUT - 3 * MINUTE]
        reading = compute_breadth({"a": holed, "b": falling()}, end_time=CUT, universe_size=2)
        assert reading.covered == 1
        assert reading.coverage == Decimal("0.5000")
        assert reading.reason == REASON_INSUFFICIENT_COVERAGE


class TestNaoAntecipacao:
    """A prova que a S1 exige: a leitura não muda quando uma vela tardia muda."""

    def test_uma_vela_um_minuto_tarde_demais_nao_entra(self) -> None:
        """A vela que **abre** no corte fecha depois dele. Ela existe no dicionário
        (o coletor pode estar à frente do produtor) e não move nada."""
        base = {f"m{i}": (falling() if i < 3 else rising()) for i in range(4)}
        before = compute_breadth(base, end_time=CUT, universe_size=4)

        late = {market: dict(closes) for market, closes in base.items()}
        for market, closes in late.items():
            # Um colapso violento no minuto que ainda está imprimindo.
            closes[CUT] = Decimal("1") if market != "m3" else Decimal("500")
        after = compute_breadth(late, end_time=CUT, universe_size=4)

        assert after == before
        assert before.value == Decimal("0.7500")

    def test_mudar_a_vela_tardia_de_todos_os_mercados_nao_move_o_numero(self) -> None:
        """A mesma prova no formato "vela não final muda, feature não muda"
        (``test_no_lookahead.py``): duas versões do futuro, uma leitura só."""
        base = {f"m{i}": (falling() if i < 194 else rising()) for i in range(200)}
        crash = {m: {**c, CUT: Decimal("1")} for m, c in base.items()}
        moon = {m: {**c, CUT: Decimal("1000")} for m, c in base.items()}
        assert (
            compute_breadth(crash, end_time=CUT, universe_size=200).value
            == compute_breadth(moon, end_time=CUT, universe_size=200).value
            == Decimal("0.9700")
        )

    def test_uma_vela_mais_velha_que_a_janela_tambem_nao_entra(self) -> None:
        """O outro lado: o fechamento de ``corte-6min`` é a referência, e um
        fechamento anterior a ele não a substitui."""
        stretched = {**falling(), CUT - 7 * MINUTE: Decimal("1")}
        reading = compute_breadth({"a": stretched}, end_time=CUT, universe_size=1)
        assert reading.falling == 1
        assert reading.covered == 1
