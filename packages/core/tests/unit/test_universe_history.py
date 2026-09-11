"""The shared membership rule (T3.88): the boundary, and what it is a boundary of.

No database: :func:`hunter_core.universe.has_min_history` is pure and
:class:`~hunter_core.universe.HistoryUniverse` derives every set it publishes from
the members it was handed, so the whole rule can be held still without a session.
The query itself is proved against a real Postgres by
``services/scanner-worker/tests/test_breadth_job.py`` (the producer's universe)
and ``services/strategy-worker/tests/test_universe_gate.py`` (the shadow gate's).

Every expected value here is written by hand. The point of the file is that the
two workers cannot disagree about "the sixteen", so a test that asked the function
what it thought would prove nothing.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from hunter_core.universe import HistoryUniverse, UniverseMember, has_min_history

pytestmark = pytest.mark.unit

AS_OF = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
NINETY_DAYS = timedelta(days=90)


def _member(symbol: str, first: datetime | None) -> UniverseMember:
    return UniverseMember(
        market_id=uuid.uuid5(uuid.NAMESPACE_OID, symbol),
        exchange="binance",
        symbol=symbol,
        first_candle_open_time=first,
    )


class TestOLimiteDeHistorico:
    """The boundary is inclusive, and "no candle" is never history."""

    def test_sem_nenhuma_vela_nunca_entra(self) -> None:
        assert has_min_history(None, as_of=AS_OF, min_history_days=90) is False

    def test_exatamente_noventa_dias_entra(self) -> None:
        """``<=``: the convention T3.82 chose, and the one T3.88 had to keep byte
        for byte or every market at the edge would have silently left the shadow
        universe the day the rule moved packages."""
        assert has_min_history(AS_OF - NINETY_DAYS, as_of=AS_OF, min_history_days=90) is True

    def test_um_segundo_a_menos_de_noventa_dias_fica_fora(self) -> None:
        short = AS_OF - NINETY_DAYS + timedelta(seconds=1)
        assert has_min_history(short, as_of=AS_OF, min_history_days=90) is False

    def test_zero_dias_admite_qualquer_historico(self) -> None:
        """``0`` is the arithmetic of "no window" — ``breadth_v1``'s universe and
        the shadow gate's disabled value read the same number the same way."""
        assert has_min_history(AS_OF, as_of=AS_OF, min_history_days=0) is True


class TestOUniversoDerivado:
    """One load, four views, and the numbers a heartbeat prints."""

    def test_dezesseis_de_duzentos_e_um_recorte_do_mesmo_load(self) -> None:
        """The shape the VPS measured on 2026-09-10, in miniature: five
        candidates, two of them with ninety days. ``candidate_keys`` is the
        denominator and never shrinks to the eligible set — that distinction is
        the whole of "16 de 200"."""
        old_a = _member("AUSDT", AS_OF - NINETY_DAYS)
        old_b = _member("BUSDT", AS_OF - timedelta(days=400))
        young = _member("CUSDT", AS_OF - timedelta(days=11))
        edge = _member("DUSDT", AS_OF - NINETY_DAYS + timedelta(minutes=1))
        empty = _member("EUSDT", None)
        universe = HistoryUniverse(
            as_of=AS_OF,
            min_history_days=90,
            members=(old_a, old_b, young, edge, empty),
        )

        assert len(universe.candidate_keys) == 5
        assert universe.eligible_keys == {("binance", "AUSDT"), ("binance", "BUSDT")}
        assert universe.eligible_ids == (old_a.market_id, old_b.market_id)
        assert len(universe.eligible) == 2

    def test_a_ordem_dos_ids_e_a_ordem_dos_membros(self) -> None:
        """``eligible_ids`` feeds ``= ANY(:market_ids)`` in the breadth producer
        and the coverage report; both must see the same list in the same order for
        the same database state, so the property preserves the load's order rather
        than a set's."""
        first = _member("AUSDT", AS_OF - timedelta(days=200))
        second = _member("ZUSDT", AS_OF - timedelta(days=100))
        universe = HistoryUniverse(as_of=AS_OF, min_history_days=90, members=(first, second))

        assert universe.eligible_ids == (first.market_id, second.market_id)

    def test_a_mesma_janela_com_zero_dias_admite_todo_mundo_com_vela(self) -> None:
        """``breadth_v1``'s universe read through the same object: the market with
        no candle at all still does not enter, because "monitored" is about the
        market and "eligible" is about evidence."""
        universe = HistoryUniverse(
            as_of=AS_OF,
            min_history_days=0,
            members=(_member("AUSDT", AS_OF), _member("EUSDT", None)),
        )

        assert universe.eligible_keys == {("binance", "AUSDT")}
