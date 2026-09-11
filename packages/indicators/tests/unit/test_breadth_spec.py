"""``breadth_v1`` and ``breadth_v2`` are two series, not two readings (T3.88).

The arithmetic is proved by ``test_breadth_series.py`` and is **unchanged** — this
file is about the other half of what a version names: the universe. Every number
below is written by hand, and two of them are the whole point of the task:
``breadth_v1`` requires no history and ``breadth_v2`` requires ninety days.

Run:
    uv run pytest packages/indicators/tests/unit/test_breadth_spec.py -q
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from hunter_indicators.breadth import (
    BREADTH_V1,
    BREADTH_V2,
    CURRENT_BREADTH_VERSION,
    MIN_COVERAGE,
    SHADOW_UNIVERSE_DAYS,
    SPECS,
    WINDOW_MINUTES,
    compute_breadth,
    current_spec,
    spec_for,
    window_open_times,
)

pytestmark = pytest.mark.unit

END = datetime(2026, 9, 11, 12, 6, tzinfo=UTC)


class TestAsDuasSeries:
    def test_v1_nao_pede_historico_e_v2_pede_noventa_dias(self) -> None:
        assert SPECS[BREADTH_V1].min_history_days == 0
        assert SPECS[BREADTH_V1].restricted is False
        assert SPECS[BREADTH_V2].min_history_days == 90
        assert SPECS[BREADTH_V2].restricted is True
        assert SHADOW_UNIVERSE_DAYS == 90

    def test_a_atual_e_a_v2_e_v1_continua_existindo(self) -> None:
        """v2 becomes the default and v1 is **not** deleted: the rows written
        under it keep a spec that describes them, which is what makes them
        readable a month from now instead of merely present."""
        assert CURRENT_BREADTH_VERSION == BREADTH_V2
        assert current_spec() is SPECS[BREADTH_V2]
        assert sorted(SPECS) == ["breadth_v1", "breadth_v2"]

    def test_a_regra_do_universo_viaja_como_palavra_auditavel(self) -> None:
        """``inputs.universe_rule`` is stored next to every row; the two strings
        must differ, or a reader could not tell the two folds apart from the row
        alone."""
        assert SPECS[BREADTH_V1].universe_rule == "monitored_perpetual"
        assert SPECS[BREADTH_V2].universe_rule == "monitored_perpetual_min_history_90d"

    def test_a_janela_e_o_piso_sao_os_mesmos_nas_duas(self) -> None:
        """T3.88 changed the universe and **nothing else**: same five minutes,
        same 80 % floor. A version that also moved the floor would be a third
        series, and this assertion is what would fail if someone tried."""
        for spec in SPECS.values():
            assert spec.window_minutes == WINDOW_MINUTES == 5
            assert spec.min_coverage == MIN_COVERAGE == Decimal("0.80")

    def test_uma_versao_desconhecida_e_recusada_nomeando_as_que_existem(self) -> None:
        with pytest.raises(KeyError) as raised:
            spec_for("breadth_v3")
        assert "breadth_v1" in str(raised.value)
        assert "breadth_v2" in str(raised.value)


class TestOMesmoMinutoDuasRespostas:
    """Why the version must be in the key: the same minute, two universes, two
    numbers — and neither one is wrong."""

    def test_dezesseis_mercados_e_duzentos_dao_valores_diferentes(self) -> None:
        """Ten markets answer, eight of them falling. Read as a universe of ten
        (``breadth_v2``'s shape: everyone in the universe has history) the fold is
        usable and worth 0,8000. Read as a universe of two hundred
        (``breadth_v1``'s shape on 2026-06-12, when only sixteen had candles) the
        coverage is 5 % and the answer is ``insufficient_coverage`` with no value
        at all. One minute, one set of candles, two honest answers — which is
        exactly why ``market_breadth`` keys on ``breadth_version``.
        """
        window = window_open_times(END)
        closes = {
            f"M{index}": dict.fromkeys(window, Decimal("100"))
            | {window[-1]: Decimal("99") if index < 8 else Decimal("101")}
            for index in range(10)
        }

        narrow = compute_breadth(closes, end_time=END, universe_size=10)
        wide = compute_breadth(closes, end_time=END, universe_size=200)

        assert narrow.usable is True
        assert narrow.covered == 10
        assert narrow.falling == 8
        assert narrow.value == Decimal("0.8000")
        assert wide.usable is False
        assert wide.value is None
        assert wide.coverage == Decimal("0.0500")
        assert wide.reason == "insufficient_coverage"
