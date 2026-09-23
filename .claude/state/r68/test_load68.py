"""Provas do carregador do R68. A que importa: a estratégia batoteira é apanhada."""

from __future__ import annotations

import numpy as np
import pytest

from load68 import Bars, LookAheadError, aggregate, assert_causal, forward


def synth(n_min: int = 120, start: int = 1000, drop: set[int] | None = None):
    drop = drop or set()
    minutes = np.array([start + i for i in range(n_min) if i not in drop], dtype=np.int64)
    k = minutes.size
    close = np.arange(1, k + 1, dtype=np.float64) * 10.0
    return dict(
        symbol="SYNTH", minutes=minutes, close=close, high=close + 1.0, low=close - 1.0,
        volume=np.full(k, 2.0), trade_count=np.full(k, 3.0), taker_buy=np.full(k, 1.0),
    )


def test_aggregate_known_values() -> None:
    """5 velas de 1 m com fechos 10..50 viram uma barra 5 m: close 50, high 51, vol 10."""
    b = aggregate(**synth(n_min=10, start=1000), h=5)
    assert len(b) == 2
    assert b.bucket_start.tolist() == [1000, 1005]
    assert b.close.tolist() == [50.0, 100.0]
    assert b.high.tolist() == [51.0, 101.0]
    assert b.low.tolist() == [9.0, 59.0]
    assert b.volume.tolist() == [10.0, 10.0]
    assert b.trade_count.tolist() == [15.0, 15.0]
    assert b.close_time.tolist() == [1005, 1010]


def test_incomplete_bucket_disappears() -> None:
    """Falta um minuto no primeiro bucket -> o bucket não existe (nada interpolado)."""
    b = aggregate(**synth(n_min=10, start=1000, drop={2}), h=5)
    assert b.bucket_start.tolist() == [1005]


def test_guard_accepts_a_source_that_closes_at_the_decision_instant() -> None:
    assert_causal(np.array([100, 95]), 100, "ok")


def test_guard_refuses_a_source_that_closes_after_the_decision_instant() -> None:
    with pytest.raises(LookAheadError):
        assert_causal(np.array([100, 101]), 100, "batota")


def test_cheat_strategy_is_caught_by_take() -> None:
    """A 'estratégia batoteira' lê a barra seguinte. `Bars.take` recusa."""
    b = aggregate(**synth(n_min=100, start=1000), h=5)
    dec = np.arange(1, len(b) - 1)
    honest = b.take(b.close, dec - 1, dec)  # barra anterior: legítimo
    assert honest.shape == dec.shape
    with pytest.raises(LookAheadError):
        b.take(b.close, dec + 1, dec)  # a vela que ainda não fechou


def test_feature_does_not_change_when_a_non_final_candle_changes() -> None:
    """O requisito do PIPELINE §2: uma bar-feature não vê a vela em formação.

    Aqui a 'vela em formação' é o minuto que ainda não fecha o bucket. Mudá-lo não
    pode alterar nenhuma feature já calculada até ao corte anterior.
    """
    base = synth(n_min=100, start=1000)
    b1 = aggregate(**base, h=5)
    mutated = {**base, "close": base["close"].copy(), "high": base["high"].copy()}
    mutated["close"][-3:] *= 7.0   # os 3 minutos do bucket incompleto/último
    mutated["high"][-3:] *= 7.0
    b2 = aggregate(**mutated, h=5)
    cut = len(b1) - 1  # tudo até à penúltima barra fechada
    dec = np.arange(1, cut)
    f1 = b1.take(b1.close, dec - 1, dec)
    f2 = b2.take(b2.close, dec - 1, dec)
    assert np.array_equal(f1, f2)


def test_forward_censors_a_gap_instead_of_filling_it() -> None:
    """Sem a barra contígua seguinte não há desfecho: o ponto some, não vira zero."""
    b = aggregate(**synth(n_min=30, start=1000, drop={10, 11, 12, 13, 14}), h=5)
    i, ret, mfe = forward(b)
    starts = b.bucket_start[i]
    assert 1005 not in starts.tolist()  # o bucket seguinte (1010) não existe
    assert ret.size == mfe.size == i.size
    assert np.all(np.isfinite(ret))


def test_forward_known_return() -> None:
    b = aggregate(**synth(n_min=10, start=1000), h=5)
    i, ret, mfe = forward(b)
    assert i.tolist() == [0]
    assert ret[0] == pytest.approx(100.0 / 50.0 - 1.0)
    assert mfe[0] == pytest.approx(101.0 / 50.0 - 1.0)
