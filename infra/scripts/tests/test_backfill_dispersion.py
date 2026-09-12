"""Unit tests for ``infra/scripts/dispersion_windows.py`` — which minutes a
``market_dispersion`` backfill is allowed to fold.

No database: the rule is pure, and it has to be, because the thing it prevents is
irreversible. ``0020`` grants nobody ``UPDATE`` or ``DELETE`` on
``market_dispersion``, so a minute folded over a day with no candles lands as a
``reason = 'insufficient_coverage'`` (or ``'btc_missing'``) row that stays there
forever in ``dispersion_24h_v1``. At a **24 h horizon** the cost of getting this
wrong is a whole day of tombstones and not a handful of minutes, which is why the
second and third rules exist at all.

Run:
    uv run pytest infra/scripts/tests/test_backfill_dispersion.py -q
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:  # the layout every script in this folder uses
    sys.path.insert(0, str(SCRIPTS_DIR))

from dispersion_windows import (  # noqa: E402  (path surgery must come first)
    days_above_the_floor,
    foldable_days,
)

FLOOR = Decimal("0.80")
UNIVERSE = 16
"""The series' universe: 16 markets, so the floor is 12,8 -> **13 dense markets**.
The numbers below are picked around that edge on purpose."""


@dataclass(frozen=True)
class _Row:
    """One row of the coverage report as it arrives: ``day`` is a
    ``date_trunc('day', open_time)``, therefore a UTC-midnight timestamp."""

    day: datetime
    dense_markets: int


def _row(day: int, dense: int) -> _Row:
    return _Row(day=datetime(2026, 9, day, tzinfo=UTC), dense_markets=dense)


def _day(day: int) -> date:
    return date(2026, 9, day)


def _days(*days: int) -> set[date]:
    return {_day(day) for day in days}


class TestOPisoDeCobertura:
    def test_treze_de_dezesseis_passa_e_doze_nao(self) -> None:
        """13/16 = 0,8125 >= 0,80; 12/16 = 0,75 < 0,80. O piso é ``>=``."""
        rows = [_row(1, 13), _row(2, 12), _row(3, 16)]
        assert days_above_the_floor(rows, universe=UNIVERSE, floor=FLOOR) == _days(1, 3)

    def test_um_dia_ausente_do_relatorio_nunca_passa(self) -> None:
        """Ausente do relatório = nenhuma vela naquele dia."""
        rows = [_row(1, 16), _row(3, 16)]
        above = days_above_the_floor(rows, universe=UNIVERSE, floor=FLOOR)
        assert _day(2) not in above

    def test_universo_vazio_nao_e_um_piso_que_alguem_alcanca(self) -> None:
        assert days_above_the_floor([_row(1, 0)], universe=0, floor=FLOOR) == set()

    def test_o_piso_e_argumento_e_nao_a_constante_da_amplitude(self) -> None:
        """A prova de que as duas séries podem divergir: com um piso de 0,50 o dia
        de 12 mercados densos passa a valer."""
        rows = [_row(1, 12)]
        assert days_above_the_floor(rows, universe=UNIVERSE, floor=FLOOR) == set()
        assert days_above_the_floor(rows, universe=UNIVERSE, floor=Decimal("0.50")) == _days(1)


class TestAVesperaCoberta:
    """A regra própria desta série: o minuto alcança o dia anterior."""

    def test_o_dia_mais_velho_de_uma_corrida_nunca_e_dobrado(self) -> None:
        """Três dias seguidos acima do piso dobram **dois**: o primeiro não tem
        véspera dentro do relatório, e todo minuto dele leria velas de fora dele."""
        above = _days(1, 2, 3)
        assert foldable_days(above, reference_days=above) == _days(2, 3)

    def test_um_buraco_no_meio_custa_o_dia_seguinte_tambem(self) -> None:
        """01, 02, [buraco em 03], 04, 05: dobram 02 e 05. O dia 04 está acima do
        piso e **não** é dobrável — as 1 440 leituras dele alcançariam o dia 03."""
        above = _days(1, 2, 4, 5)
        assert foldable_days(above, reference_days=above) == _days(2, 5)

    def test_um_dia_isolado_nao_dobra_nada(self) -> None:
        assert foldable_days(_days(7), reference_days=_days(7)) == set()

    def test_noventa_dias_contiguos_dobram_oitenta_e_nove(self) -> None:
        """O número declarado no docstring do CLI, medido: ``--days 90`` dobra 89."""
        above = {
            date(2026, 6, 14) + (date(2026, 6, 15) - date(2026, 6, 14)) * step for step in range(90)
        }
        assert len(above) == 90
        assert len(foldable_days(above, reference_days=above)) == 89


class TestAReferenciaDensa:
    """Sem BTC no dia (ou na véspera dele) a dobra é 1 440 lápides de ``btc_missing``."""

    def test_um_dia_sem_a_referencia_nao_e_dobravel_mesmo_acima_do_piso(self) -> None:
        above = _days(1, 2, 3)
        assert foldable_days(above, reference_days=_days(1, 3)) == set()

    def test_a_referencia_ausente_na_vespera_tambem_barra_o_dia(self) -> None:
        """A referência existe no dia 3 e não no dia 2: o dia 3 lê o fechamento de
        24 h atrás no dia 2, então ele não é dobrável."""
        above = _days(1, 2, 3)
        assert foldable_days(above, reference_days=_days(1, 3)) == set()
        assert foldable_days(above, reference_days=_days(1, 2)) == _days(2)

    def test_sem_referencia_nenhuma_nada_e_dobravel(self) -> None:
        assert foldable_days(_days(1, 2, 3), reference_days=set()) == set()


class TestAsTresRegrasJuntas:
    def test_o_conjunto_dobravel_nunca_cresce_alem_do_que_passa_o_piso(self) -> None:
        """Invariante que vale a pena travar: ``keep`` é sempre subconjunto de
        ``above``, então o operador nunca vê um dia dobrado que o relatório
        reprovou."""
        above = _days(1, 2, 3, 5, 6)
        keep = foldable_days(above, reference_days=_days(1, 2, 3, 5, 6, 7))
        assert keep <= above
        assert keep == _days(2, 3, 6)
