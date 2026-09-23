"""A prova mais valiosa do moinho: a estratégia batoteira é apanhada.

Porta o `test_load68.py` do R68 (`.claude/state/r68/test_load68.py`) e os casos de
observabilidade do R69 (`.claude/state/r69/test_cohort.py`) para a guarda genérica.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from infra.research.guards import (
    GuardedSeries,
    Instants,
    LookAheadError,
    assert_causal,
    assert_observable,
    observable_rows,
)

T = datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)


def _series(n: int = 20, h: int = 5, start: int = 1000) -> GuardedSeries:
    """Barras fechadas de `h` minutos: `close_time` é o instante de decisão de quem a usa."""
    close_time = np.array([start + h * (i + 1) for i in range(n)], dtype=np.int64)
    values = np.arange(1, n + 1, dtype=np.float64) * 10.0
    return GuardedSeries(name="SYNTH/h5", close_time=close_time, values=values)


# --------------------------------------------------------------------------- séries


def test_guard_accepts_a_source_that_closes_at_the_decision_instant() -> None:
    assert_causal(np.array([100, 95]), 100, "ok")


def test_guard_refuses_a_source_that_closes_after_the_decision_instant() -> None:
    with pytest.raises(LookAheadError):
        assert_causal(np.array([100, 101]), 100, "batota")


def test_honest_strategy_reads_the_previous_bar() -> None:
    s = _series()
    dec = np.arange(1, len(s) - 1)
    assert s.take(dec - 1, dec).shape == dec.shape
    assert s.take(dec, dec).shape == dec.shape  # a própria barra já fechada é legítima


def test_cheat_strategy_is_caught() -> None:
    """A estratégia batoteira lê a barra seguinte — a que ainda não fechou."""
    s = _series()
    dec = np.arange(1, len(s) - 1)
    with pytest.raises(LookAheadError, match="fecha em"):
        s.take(dec + 1, dec)


def test_cheat_on_a_single_row_is_caught() -> None:
    """Uma só linha adiantada no meio de mil honestas basta para levantar."""
    s = _series(n=1000)
    dec = np.arange(1, 999)
    idx = dec - 1
    idx[500] = dec[500] + 1
    with pytest.raises(LookAheadError):
        s.take(idx, dec)


def test_feature_does_not_change_when_a_non_final_row_changes() -> None:
    """PIPELINE §2: uma bar-feature não vê a vela em formação.

    A 'vela em formação' aqui é a última barra da série. Mudá-la não pode alterar
    nenhuma feature lida até ao corte anterior.
    """
    s1 = _series(n=40)
    mutated = s1.values.copy()
    mutated[-1] *= 7.0
    s2 = GuardedSeries(name=s1.name, close_time=s1.close_time, values=mutated)
    dec = np.arange(1, len(s1) - 1)
    assert np.array_equal(s1.take(dec - 1, dec), s2.take(dec - 1, dec))


def test_appending_future_rows_does_not_change_past_features() -> None:
    s1 = _series(n=20)
    s2 = _series(n=40)
    dec = np.arange(1, 18)
    assert np.array_equal(s1.take(dec - 1, dec), s2.take(dec - 1, dec))


# ------------------------------------------------------------------- observabilidade


def _inst(as_of_s: int, computed_s: int | None = None, tape_s: int | None = None) -> Instants:
    as_of = T + timedelta(seconds=as_of_s)
    return Instants(
        as_of=as_of,
        computed_at=as_of if computed_s is None else T + timedelta(seconds=computed_s),
        tape_as_of=as_of if tape_s is None else T + timedelta(seconds=tape_s),
    )


def test_row_observed_before_the_decision_passes() -> None:
    assert_observable(_inst(-15), T, "ok")


def test_row_observed_after_the_decision_raises() -> None:
    with pytest.raises(LookAheadError, match="as_of"):
        assert_observable(_inst(+1), T, "tique do futuro")


def test_row_written_after_the_decision_raises() -> None:
    """as_of anterior à decisão mas computed_at posterior: preenchimento retroativo."""
    with pytest.raises(LookAheadError, match="computed_at"):
        assert_observable(_inst(-20, computed_s=+5), T, "escrita retroativa")


def test_tape_from_the_future_of_its_own_row_raises() -> None:
    with pytest.raises(LookAheadError, match="tape_as_of"):
        assert_observable(_inst(-20, tape_s=+10), T, "fita adiantada")


def test_lag_refuses_rows_inside_the_lag() -> None:
    assert_observable(_inst(-30), T, "ok", lag=timedelta(seconds=20))
    with pytest.raises(LookAheadError):
        assert_observable(_inst(-10), T, "dentro do atraso", lag=timedelta(seconds=20))


def test_naive_datetimes_are_refused() -> None:
    naive = datetime(2026, 9, 20, 11, 59, 0)  # noqa: DTZ001 — o ponto do teste
    with pytest.raises(ValueError, match="UTC"):
        assert_observable(Instants(naive, naive, None), T, "sem fuso")


def test_missing_tape_is_allowed_and_declared() -> None:
    assert_observable(Instants(_inst(-5).as_of, _inst(-5).computed_at, None), T, "sem fita")


# ------------------------------------------------------------------- linhas em lote


def test_observable_rows_splits_kept_from_refused() -> None:
    rows = [
        {"t": T, "a": T - timedelta(seconds=5), "c": T - timedelta(seconds=5)},
        {"t": T, "a": T + timedelta(seconds=5), "c": T + timedelta(seconds=5)},
    ]
    kept, refused = observable_rows(rows, decision="t", as_of="a", computed_at="c")
    assert len(kept) == 1
    assert len(refused) == 1
    assert "as_of" in refused[0][1]


def test_observable_rows_raises_when_told_to() -> None:
    rows = [{"t": T, "a": T + timedelta(seconds=5), "c": T + timedelta(seconds=5)}]
    with pytest.raises(LookAheadError):
        observable_rows(rows, decision="t", as_of="a", computed_at="c", strict=True)
