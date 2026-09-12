"""``dispersion_24h``'s arithmetic, with every expected number worked out by hand.

T3.90 / H-P18. The subject is :func:`hunter_indicators.dispersion.compute_dispersion`
and nothing else: no database, no clock, no universe query. Every expectation
below is a literal computed on paper (the fractions are chosen so the decimals
terminate), because a test that asks the function what it thinks the answer is
would pass no matter what the arithmetic did.

Run: ``uv run pytest packages/indicators/tests/unit/test_dispersion_series.py -q``
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_indicators.dispersion import (
    HORIZON_MINUTES,
    REASON_EMPTY_UNIVERSE,
    REASON_INSUFFICIENT_COVERAGE,
    REASON_NO_ALTS,
    REASON_REFERENCE_MISSING,
    compute_dispersion,
    endpoint_open_times,
    median,
)

pytestmark = pytest.mark.unit

MINUTE = timedelta(minutes=1)
END = datetime(2026, 9, 11, 12, 6, tzinfo=UTC)
OLD, NEW = endpoint_open_times(END)

BTC = "BTCUSDT"


def market(*, old: str, new: str) -> dict[datetime, Decimal]:
    """One market's two endpoint closes, and nothing else."""
    return {OLD: Decimal(old), NEW: Decimal(new)}


class TestOsDoisInstantes:
    """A janela é um par de instantes, e é isso que impede a antecipação."""

    def test_os_instantes_sao_o_fechamento_do_corte_e_o_de_24_h_antes(self) -> None:
        """A vela mais nova admitida **fecha** exatamente no corte, logo abre um
        minuto antes; a mais velha fecha 1 440 min antes disso."""
        assert NEW == END - MINUTE
        assert OLD == END - MINUTE * (HORIZON_MINUTES + 1)
        assert NEW - OLD == timedelta(minutes=HORIZON_MINUTES)

    def test_a_vela_que_abre_no_corte_nunca_e_pedida(self) -> None:
        assert END not in endpoint_open_times(END)

    def test_um_horizonte_menor_que_um_minuto_e_recusado(self) -> None:
        with pytest.raises(ValueError, match="at least 1"):
            endpoint_open_times(END, 0)


class TestAMediana:
    """Mediana, não média: uma memecoin de +400 % não vira "as alts"."""

    def test_impar_e_o_valor_do_meio(self) -> None:
        values = [Decimal("-0.05"), Decimal("-0.01"), Decimal("0.30")]
        assert median(values) == Decimal("-0.010000")

    def test_par_e_a_media_dos_dois_do_meio(self) -> None:
        values = [Decimal("-0.06"), Decimal("-0.04"), Decimal("-0.02"), Decimal("0.10")]
        assert median(values) == Decimal("-0.030000")

    def test_um_outlier_absurdo_nao_move_a_mediana(self) -> None:
        """O mesmo conjunto com o maior valor trocado por +400 %: a mediana não
        se move um dígito. Uma média se moveria de -0,03 para +0,9733."""
        base = [Decimal("-0.06"), Decimal("-0.04"), Decimal("-0.02"), Decimal("0.10")]
        wild = [Decimal("-0.06"), Decimal("-0.04"), Decimal("-0.02"), Decimal("4.00")]
        assert median(base) == median(wild) == Decimal("-0.030000")

    def test_mediana_de_nada_e_um_erro_nao_um_zero(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            median([])


class TestODiaDoPlantao:
    """O número que motivou a hipótese, reproduzido com preços exatos."""

    def test_a_discordancia_de_dez_de_setembro(self) -> None:
        """BTC -1,50 % e a mediana das alts -4,80 %: dispersão -0,033000, e as
        cinco alts ficam **abaixo** do BTC, logo ``share_below_btc`` = 1,0000.

        Os preços são escolhidos para o retorno terminar: 100 -> 98,5 é
        -0,015000 exato; 100 -> 95,2 é -0,048000 exato.
        """
        closes = {
            BTC: market(old="100", new="98.5"),
            "A": market(old="100", new="95.0"),
            "B": market(old="100", new="95.1"),
            "C": market(old="100", new="95.2"),
            "D": market(old="100", new="95.3"),
            "E": market(old="100", new="95.4"),
        }

        reading = compute_dispersion(closes, end_time=END, reference=BTC, universe_size=6)

        assert reading.usable is True
        assert reading.reason is None
        assert reading.covered == 6
        assert reading.alts_covered == 5
        assert reading.btc_r24h == Decimal("-0.015000")
        assert reading.median_alt_r24h == Decimal("-0.048000")
        assert reading.dispersion == Decimal("-0.033000")
        assert reading.alts_below_btc == 5
        assert reading.share_below_btc == Decimal("1.0000")
        assert reading.coverage == Decimal("1.0000")

    def test_a_identidade_dispersao_igual_mediana_menos_btc_vale_sempre(self) -> None:
        """A CHECK da ``0020`` depende disto: as três colunas são coerentes ao
        sexto decimal porque a subtração é feita **depois** de quantizar."""
        closes = {
            BTC: market(old="3", new="4"),  # +0,333333...
            "A": market(old="7", new="9"),  # +0,285714...
            "B": market(old="11", new="13"),  # +0,181818...
            "C": market(old="6", new="7"),  # +0,166666...
        }

        reading = compute_dispersion(closes, end_time=END, reference=BTC, universe_size=4)

        btc, middle = reading.btc_r24h, reading.median_alt_r24h
        assert btc == Decimal("0.333333")
        assert middle == Decimal("0.181818")  # o do meio de três
        assert btc is not None and middle is not None
        assert reading.dispersion == Decimal("-0.151515") == middle - btc


class TestQuemNaoTemOsDoisFechamentos:
    """A regra do fechamento ausente: fora da conta, e contado como faltante."""

    def test_faltando_a_ponta_nova_o_mercado_nao_entra_nem_no_numerador_nem_no_n(
        self,
    ) -> None:
        """Cinco mercados declarados. ``GONE`` tem só o fechamento velho e
        ``LATE`` só o novo — os dois **cairiam forte** se entrassem (-50 % e
        -90 %) e mudariam a mediana de -0,020000 para -0,500000. Cobertura
        3/5 = 0,6000, abaixo do piso: a leitura recusa e diz por quê."""
        closes = {
            BTC: market(old="100", new="99"),
            "A": market(old="100", new="98"),
            "B": market(old="100", new="97"),
            "GONE": {OLD: Decimal("100")},
            "LATE": {NEW: Decimal("10")},
        }

        reading = compute_dispersion(closes, end_time=END, reference=BTC, universe_size=5)

        assert reading.covered == 3
        assert reading.alts_covered == 2
        assert reading.coverage == Decimal("0.6000")
        assert reading.usable is False
        assert reading.reason == REASON_INSUFFICIENT_COVERAGE
        assert reading.dispersion is None
        assert reading.median_alt_r24h is None
        assert reading.btc_r24h is None
        assert reading.share_below_btc is None

    def test_um_fechamento_velho_zerado_conta_como_ausente(self) -> None:
        """Zero não é preço: dividir por ele não é um número, e a resposta
        honesta é a mesma da vela que não existe."""
        closes = {
            BTC: market(old="100", new="99"),
            "A": market(old="100", new="98"),
            "ZERO": {OLD: Decimal("0"), NEW: Decimal("50")},
        }

        reading = compute_dispersion(closes, end_time=END, reference=BTC, universe_size=3)

        assert reading.covered == 2
        assert reading.alts_covered == 1
        assert reading.coverage == Decimal("0.6667")
        assert reading.reason == REASON_INSUFFICIENT_COVERAGE


class TestNaoAntecipacao:
    """A prova que o brief pede: uma vela um minuto atrasada não move nada."""

    def test_uma_vela_que_abre_no_corte_nao_muda_a_leitura(self) -> None:
        """O mesmo fold, uma vez sem e uma vez com a vela que **abre** no corte
        (fecha depois dele) valendo um quedaço. Byte a byte a mesma leitura — e
        o valor extra é grande de propósito: se entrasse, a dispersão sairia de
        -0,010000 para algo perto de -0,9."""
        clean = {
            BTC: market(old="100", new="100"),
            "A": market(old="100", new="99"),
            "B": market(old="100", new="99"),
        }
        poisoned = {
            BTC: {**clean[BTC], END: Decimal("100")},
            "A": {**clean["A"], END: Decimal("10")},
            "B": {**clean["B"], END: Decimal("10")},
        }

        before = compute_dispersion(clean, end_time=END, reference=BTC, universe_size=3)
        after = compute_dispersion(poisoned, end_time=END, reference=BTC, universe_size=3)

        assert before.dispersion == Decimal("-0.010000")
        assert before == after

    def test_uma_vela_um_minuto_mais_velha_que_a_ponta_tambem_nao_entra(self) -> None:
        """A outra ponta da mesma regra: a âncora de 24 h é **exata**, não "o
        fechamento mais próximo antes". Uma vela em ``OLD - 1min`` valendo 1 (que
        faria o retorno explodir para +9 800 %) é ignorada, e o mercado que só
        tem *ela* como ponta velha fica de fora."""
        closes = {
            BTC: {**market(old="100", new="99"), OLD - MINUTE: Decimal("1")},
            "A": {**market(old="100", new="98"), OLD - MINUTE: Decimal("1")},
            "NEARLY": {OLD - MINUTE: Decimal("100"), NEW: Decimal("50")},
        }

        reading = compute_dispersion(closes, end_time=END, reference=BTC, universe_size=2)

        assert reading.covered == 2  # NEARLY is not counted at all
        assert reading.btc_r24h == Decimal("-0.010000")
        assert reading.median_alt_r24h == Decimal("-0.020000")
        assert reading.dispersion == Decimal("-0.010000")


class TestShareBelowBtc:
    """A fração abaixo do BTC: ``<`` estrito, empate não conta."""

    def test_empate_com_o_btc_nao_conta_como_abaixo(self) -> None:
        """Quatro alts: duas abaixo, uma **igual** ao BTC e uma acima. 2/4 =
        0,5000 — a igual do meio é a prova de que o ``<`` é estrito."""
        closes = {
            BTC: market(old="100", new="99"),  # -0,010000
            "BELOW1": market(old="100", new="98"),  # -0,020000
            "BELOW2": market(old="100", new="97"),  # -0,030000
            "TIED": market(old="200", new="198"),  # -0,010000, o mesmo do BTC
            "ABOVE": market(old="100", new="101"),  # +0,010000
        }

        reading = compute_dispersion(closes, end_time=END, reference=BTC, universe_size=5)

        assert reading.alts_covered == 4
        assert reading.alts_below_btc == 2
        assert reading.share_below_btc == Decimal("0.5000")
        # mediana de (-0,03, -0,02, -0,01, +0,01) = (-0,02 + -0,01)/2
        assert reading.median_alt_r24h == Decimal("-0.015000")
        assert reading.dispersion == Decimal("-0.005000")


class TestOPisoDeCobertura:
    """Cobertura recusa; nunca inclina."""

    def test_exatamente_no_piso_a_leitura_vale(self) -> None:
        """4 de 5 = 0,8000, exatamente :data:`MIN_COVERAGE`: ``>=``, não ``>``."""
        closes = {
            BTC: market(old="100", new="99"),
            "A": market(old="100", new="98"),
            "B": market(old="100", new="97"),
            "C": market(old="100", new="96"),
        }

        reading = compute_dispersion(closes, end_time=END, reference=BTC, universe_size=5)

        assert reading.coverage == Decimal("0.8000")
        assert reading.usable is True
        assert reading.median_alt_r24h == Decimal("-0.030000")

    def test_um_mercado_a_menos_derruba_a_leitura(self) -> None:
        closes = {
            BTC: market(old="100", new="99"),
            "A": market(old="100", new="98"),
            "B": market(old="100", new="97"),
        }

        reading = compute_dispersion(closes, end_time=END, reference=BTC, universe_size=5)

        assert reading.coverage == Decimal("0.6000")
        assert reading.usable is False
        assert reading.reason == REASON_INSUFFICIENT_COVERAGE


class TestAPrecedenciaDasRecusas:
    """Quatro recusas, uma ordem, e ela é a do ``market_betas``."""

    def test_universo_vazio_vem_antes_de_tudo(self) -> None:
        reading = compute_dispersion({}, end_time=END, reference=BTC, universe_size=0)
        assert reading.reason == REASON_EMPTY_UNIVERSE
        assert reading.coverage == Decimal("0")

    def test_sem_referencia_no_universo_a_recusa_e_btc_missing(self) -> None:
        """Cobertura perfeita (2/2) e nenhuma referência declarada: não há o que
        medir *contra*."""
        closes = {"A": market(old="100", new="98"), "B": market(old="100", new="97")}

        reading = compute_dispersion(closes, end_time=END, reference=None, universe_size=2)

        assert reading.coverage == Decimal("1.0000")
        assert reading.reason == REASON_REFERENCE_MISSING
        assert reading.alts_below_btc == 0  # ninguém está abaixo de um número que não existe

    def test_referencia_sem_vela_vem_antes_da_cobertura(self) -> None:
        """O BTC está no universo e perdeu uma ponta; a cobertura também caiu.
        A palavra é ``btc_missing`` — a mais específica, e a que o operador age
        sobre — exatamente a precedência do ``beta_repo``."""
        closes = {
            BTC: {OLD: Decimal("100")},
            "A": market(old="100", new="98"),
        }

        reading = compute_dispersion(closes, end_time=END, reference=BTC, universe_size=5)

        assert reading.coverage == Decimal("0.2000")
        assert reading.reason == REASON_REFERENCE_MISSING

    def test_so_a_referencia_respondeu_e_a_recusa_e_no_alts(self) -> None:
        closes = {BTC: market(old="100", new="99")}

        reading = compute_dispersion(closes, end_time=END, reference=BTC, universe_size=1)

        assert reading.coverage == Decimal("1.0000")
        assert reading.reason == REASON_NO_ALTS
        assert reading.median_alt_r24h is None


class TestOQueNaoEPedidoEIgnorado:
    """Um chamador que buscou demais não alarga o horizonte por acidente."""

    def test_instantes_extras_no_meio_da_janela_nao_mudam_nada(self) -> None:
        middle = OLD + MINUTE * 700
        lean = {BTC: market(old="100", new="99"), "A": market(old="100", new="98")}
        fat = {
            BTC: {**lean[BTC], middle: Decimal("1")},
            "A": {**lean["A"], middle: Decimal("1000")},
        }

        assert compute_dispersion(
            lean, end_time=END, reference=BTC, universe_size=2
        ) == compute_dispersion(fat, end_time=END, reference=BTC, universe_size=2)
