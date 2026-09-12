"""A versão nomeia a aritmética **e** o universo **e** a referência.

T3.90. O que este arquivo prova é que ``dispersion_24h_v1`` não pode ser
reapontado em silêncio: o número de dias de histórico, a referência, o horizonte
e o piso são propriedades da *versão*, e uma versão que este build não conhece é
recusada em vez de servida pela mais próxima.

Run: ``uv run pytest packages/indicators/tests/unit/test_dispersion_spec.py -q``
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from hunter_indicators.breadth import SHADOW_UNIVERSE_DAYS as BREADTH_SHADOW_DAYS
from hunter_indicators.dispersion import (
    CURRENT_DISPERSION_VERSION,
    DISPERSION_V1,
    HORIZON_MINUTES,
    MIN_COVERAGE,
    SHADOW_UNIVERSE_DAYS,
    SPECS,
    compute_dispersion,
    current_spec,
    endpoint_open_times,
    spec_for,
)

pytestmark = pytest.mark.unit

END = datetime(2026, 9, 11, 12, 6, tzinfo=UTC)
OLD, NEW = endpoint_open_times(END)


class TestOQueAVersaoCongela:
    def test_v1_e_a_atual_e_dobra_o_universo_sombra_contra_o_btc(self) -> None:
        spec = current_spec()
        assert CURRENT_DISPERSION_VERSION == DISPERSION_V1 == "dispersion_24h_v1"
        assert spec.min_history_days == SHADOW_UNIVERSE_DAYS == 90
        assert spec.reference_symbol == "BTCUSDT"
        assert spec.horizon_minutes == HORIZON_MINUTES == 1_440
        assert spec.min_coverage == MIN_COVERAGE == Decimal("0.80")
        assert spec.restricted is True
        assert spec.universe_rule == "monitored_perpetual_min_history_90d"

    def test_uma_versao_desconhecida_e_recusada_nomeando_as_que_existem(self) -> None:
        with pytest.raises(KeyError, match="dispersion_24h_v1"):
            spec_for("dispersion_24h_v2")

    def test_o_registro_e_a_unica_fonte_do_que_este_build_le(self) -> None:
        assert set(SPECS) == {DISPERSION_V1}
        assert all(version == spec.version for version, spec in SPECS.items())


class TestDuasSeriesQueNaoSeMovemJuntas:
    def test_os_noventa_dias_sao_uma_constante_propria_desta_serie(self) -> None:
        """Hoje as duas séries valem 90, e este teste existe para que o dia em
        que a amplitude mudar de universo a decisão seja **explícita**: a
        constante desta série é definida no módulo dela
        (``dispersion.spec.SHADOW_UNIVERSE_DAYS``), não importada da amplitude,
        então mexer numa não move a outra — quem quebrar esta igualdade quebra
        este teste e tem de dizer qual das duas mudou."""
        import hunter_indicators.dispersion.spec as dispersion_spec

        assert "SHADOW_UNIVERSE_DAYS" in vars(dispersion_spec)
        assert dispersion_spec.SHADOW_UNIVERSE_DAYS == SHADOW_UNIVERSE_DAYS == 90
        assert BREADTH_SHADOW_DAYS == 90


class TestOMesmoMinutoEmDoisUniversos:
    def test_a_mesma_dispersao_vale_ou_nao_conforme_o_universo_declarado(self) -> None:
        """O mesmo fold, os mesmos preços: num universo de 5 a leitura vale
        -0,010000; num de 200 (o que a ``breadth_v1`` mediria) ela é
        ``insufficient_coverage``. É a razão de a versão nomear o universo."""
        closes = {
            "BTCUSDT": {OLD: Decimal("100"), NEW: Decimal("100")},
            "A": {OLD: Decimal("100"), NEW: Decimal("99")},
            "B": {OLD: Decimal("100"), NEW: Decimal("99")},
            "C": {OLD: Decimal("100"), NEW: Decimal("99")},
            "D": {OLD: Decimal("100"), NEW: Decimal("99")},
        }

        dense = compute_dispersion(closes, end_time=END, reference="BTCUSDT", universe_size=5)
        sparse = compute_dispersion(closes, end_time=END, reference="BTCUSDT", universe_size=200)

        assert dense.usable is True
        assert dense.dispersion == Decimal("-0.010000")
        assert sparse.usable is False
        assert sparse.reason == "insufficient_coverage"
        assert sparse.coverage == Decimal("0.0250")
