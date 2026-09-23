"""Os oito contraexemplos que a Astra reproduziu na revisão da T4.87, agora presos.

Cada teste abaixo é um veredito que o moinho dava errado antes da correção. A fonte é
`.claude/state/astra-review-t487-diff.md`; a ordem é a dos must-fix dela.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import pytest

from infra.research.guards import Instants, assert_observable
from infra.research.protocol import run_hypothesis
from infra.research.spec import (
    DecisionPolicy,
    HypothesisSpec,
    InferencePlan,
    ObservabilityColumns,
    ObservabilityWaiver,
    PreRegistration,
    PreRegistrationError,
    Split,
)
from infra.research.stats import adjust_family, check_grid, threshold_curve

T0 = datetime(2026, 9, 1, tzinfo=UTC)

PRE = PreRegistration(
    "os selecionados rendem mais +0,05",
    "IC 95 % com limite superior abaixo de +0,01",
    "CONFIRMA com IC acima de zero, p<0,05, D≥MRE, nível positivo e planalto",
    "2026-09-23",
    "fixo, congelado no pré-registo",
)
GRID = (20.0, 30.0, 40.0, 50.0, 60.0, 70.0)


def _rows(n: int = 200, effect: float = 0.5, *, days: int = 10) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i in range(n):
        t = T0 + timedelta(days=i % days, minutes=i)
        x = float((i * 37) % 100)
        rows.append(
            {
                "mint": f"m{i}",
                "t": t,
                "day": t.date().isoformat(),
                "x": x,
                "ret": (effect if x <= 50 else 0.0) + 0.05 * (1 if i % 2 else -1),
                "as_of": t - timedelta(seconds=30),
                "computed_at": t - timedelta(seconds=30),
                "tape_as_of": t - timedelta(seconds=30),
            }
        )
    return rows


def _spec(rows: list[dict[str, Any]], **over: Any) -> HypothesisSpec:
    base: dict[str, Any] = {
        "name": "H-astra",
        "origin": "contraexemplo",
        "loader": lambda: rows,
        "decision_instant": "t",
        "outcome": "ret",
        "variable": "x",
        "direction": "low",
        "observability": ObservabilityColumns("as_of", "computed_at", "tape_as_of"),
        "inference": InferencePlan("mint", "day", thresholds=GRID, reps=1200, seed=1),
        "policy": DecisionPolicy(frozen_threshold=50.0, minimum_effect=0.05),
        "pre_registration": PRE,
    }
    base.update(over)
    return HypothesisSpec(**base)


# ------------------------------------------- 1. split vazio, minúsculo ou purgado


def test_declared_split_with_an_empty_test_slice_cannot_confirm() -> None:
    """SPLIT_EMPTY: a fronteira depois de todos os dias deixava o teste vazio e passava."""
    report = run_hypothesis(_spec(_rows(), split=Split("day", "2026-12-31")))
    assert report.verdict == "NÃO CONFIRMA"
    assert "fatia de teste" in " ".join(report.reasons)


def test_declared_split_with_a_two_row_test_slice_cannot_confirm() -> None:
    """TINY_OOS: teste com n=1/1 não sustenta veredito nenhum."""
    rows = _rows(200) + [
        {**r, "day": "2026-12-01", "mint": f"z{i}"} for i, r in enumerate(_rows(2))
    ]
    report = run_hypothesis(_spec(rows, split=Split("day", "2026-11-01")))
    assert report.verdict == "NÃO CONFIRMA"
    assert "amostra insuficiente" in " ".join(report.reasons)


def test_purged_rows_no_longer_sustain_the_main_contrast() -> None:
    """PURGED_MAIN: 200 das 202 linhas do efeito estavam na purga e o veredito sobrevivia."""
    no_purge = run_hypothesis(_spec(_rows(200), split=Split("day", "2026-09-01")))
    purged = run_hypothesis(_spec(_rows(200), split=Split("day", "2026-09-01", purge=8)))
    assert purged.purged > 0
    assert purged.n_used == no_purge.n_used - purged.purged
    assert purged.verdict == "NÃO CONFIRMA"


def test_a_datetime_split_column_is_refused_instead_of_compared_as_text() -> None:
    """`2026-09-01 23:00+00` caía no treino de uma fronteira `2026-09-01T12:00:00Z`."""
    rows = [{**r, "day": r["t"]} for r in _rows(60)]
    with pytest.raises(ValueError, match="texto ordenável"):
        run_hypothesis(_spec(rows, split=Split("day", "2026-09-01T12:00:00Z")))


# ------------------------------------------------------- 2. buracos da guarda


def test_a_tape_timestamp_as_a_string_is_refused_not_ignored() -> None:
    """FUTURE_TAPE_STRING: fita um dia no futuro, em texto ISO, passava como ausente."""
    rows = [{**r, "tape_as_of": (r["t"] + timedelta(days=1)).isoformat()} for r in _rows(60)]
    with pytest.raises(ValueError, match="não é datetime"):
        run_hypothesis(_spec(rows))


def test_a_negative_lag_is_refused() -> None:
    """Subtrair um atraso negativo adiantava o corte da guarda."""
    with pytest.raises(ValueError, match="negativo"):
        assert_observable(
            Instants(T0 + timedelta(seconds=1), T0 + timedelta(seconds=1)),
            T0,
            "adiantado",
            lag=timedelta(seconds=-2),
        )
    with pytest.raises(ValueError, match="negativo"):
        run_hypothesis(
            _spec(
                _rows(60),
                observability=ObservabilityColumns(
                    "as_of", "computed_at", "tape_as_of", lag=timedelta(seconds=-2)
                ),
            )
        )


def test_an_empty_waiver_reason_is_refused() -> None:
    with pytest.raises(PreRegistrationError, match="dispensa"):
        run_hypothesis(_spec(_rows(60), observability=ObservabilityWaiver("   ")))


# ---------------------------------------------------------- 3. NaN e p ausente


def test_a_nan_outcome_is_censored_and_never_produces_a_verdict() -> None:
    """NAN_OUTCOME: um NaN no desfecho dava `REFUTA` com D = nan e censura zero."""
    rows = _rows(200)
    rows[0]["ret"] = float("nan")
    report = run_hypothesis(_spec(rows))
    assert report.censored_outcome == 1
    assert np.isfinite(report.contrast.d)
    assert report.verdict in ("CONFIRMA", "NÃO CONFIRMA", "REFUTA")


def test_a_nan_variable_is_censored_not_selected() -> None:
    rows = _rows(200)
    rows[1]["x"] = float("nan")
    assert run_hypothesis(_spec(rows)).censored_variable == 1


def test_a_family_with_a_missing_p_is_refused() -> None:
    """adjust_family([NaN, 0,001]) devolvia dois sobreviventes."""
    with pytest.raises(ValueError, match="não finito|fora de"):
        adjust_family([float("nan"), 0.001])
    with pytest.raises(ValueError, match="fora de"):
        adjust_family([1.4, 0.001])


# ------------------------------------------- 4. um único cluster no braço selecionado


def test_one_selected_cluster_cannot_confirm() -> None:
    """ONE_SELECTED_CLUSTER: 8 clusters, 1 só selecionado, IC [1,0; 1,0] e CONFIRMA."""
    rows: list[dict[str, Any]] = []
    for c in range(8):
        for j in range(25):
            t = T0 + timedelta(days=c, minutes=j)
            rows.append(
                {
                    "mint": f"c{c}",
                    "t": t,
                    "day": t.date().isoformat(),
                    "x": 10.0 if c == 0 else 90.0,
                    "ret": 1.0 if c == 0 else 0.0,
                    "as_of": t - timedelta(seconds=5),
                    "computed_at": t - timedelta(seconds=5),
                    "tape_as_of": t - timedelta(seconds=5),
                }
            )
    report = run_hypothesis(
        _spec(rows, inference=InferencePlan("mint", "day", thresholds=GRID, reps=1200, seed=2))
    )
    assert report.verdict == "NÃO CONFIRMA"
    assert "réplicas" in " ".join(report.reasons) or "descartadas" in " ".join(report.reasons)


# --------------------------------------- 5. dependência temporal declarada


def test_a_declared_block_must_also_clear_zero() -> None:
    """Efeito concentrado num bloco: IC de cluster [+0,73;+1,11] mas de bloco cobre zero."""
    rows: list[dict[str, Any]] = []
    for b in range(10):
        for j in range(30):
            t = T0 + timedelta(days=b, minutes=j)
            hi = j % 2 == 0
            rows.append(
                {
                    "mint": f"b{b}-{j}",
                    "t": t,
                    "day": t.date().isoformat(),
                    "bloco": f"b{b}",
                    "x": 10.0 if hi else 90.0,
                    "ret": (1.0 if (hi and b == 0) else 0.0),
                    "as_of": t - timedelta(seconds=5),
                    "computed_at": t - timedelta(seconds=5),
                    "tape_as_of": t - timedelta(seconds=5),
                }
            )
    plan = InferencePlan("mint", "day", "bloco", thresholds=(20.0, 50.0, 80.0), reps=1200, seed=3)
    report = run_hypothesis(
        _spec(rows, inference=plan, policy=DecisionPolicy(50.0, 0.01, require_plateau=False))
    )
    assert report.contrast.ci_block is not None
    assert report.contrast.ci_block.lo <= 0 < report.contrast.ci.lo
    assert report.verdict == "NÃO CONFIRMA"
    assert "blocos" in " ".join(report.reasons)


def test_many_rows_per_cluster_raise_a_caveat_about_the_permutation() -> None:
    rows = [{**r, "mint": f"m{i // 25}"} for i, r in enumerate(_rows(200))]
    report = run_hypothesis(_spec(rows))
    assert any("linhas por cluster" in c for c in report.caveats)


# ------------------------------------------------------------ 6. fingerprint


def test_fingerprint_changes_with_the_split_and_with_the_cluster() -> None:
    rows = _rows(60)
    base = run_hypothesis(_spec(rows)).fingerprint
    with_split = run_hypothesis(_spec(rows, split=Split("day", "2026-09-05"))).fingerprint
    other_cluster = run_hypothesis(
        _spec(rows, inference=InferencePlan("day", None, thresholds=GRID, reps=800, seed=1))
    ).fingerprint
    assert len({base, with_split, other_cluster}) == 3


# -------------------------------------------------------- 7. grelha repetida


def test_a_repeated_threshold_grid_is_refused() -> None:
    """thresholds=(50,50,50,50) passava por planalto sem testar vizinho nenhum."""
    with pytest.raises(ValueError, match="estritamente crescente"):
        run_hypothesis(
            _spec(
                _rows(200),
                inference=InferencePlan(
                    "mint", "day", thresholds=(50.0, 50.0, 50.0, 50.0), reps=800
                ),
            )
        )
    with pytest.raises(ValueError, match="estritamente crescente"):
        check_grid((10.0, 5.0))
    with pytest.raises(ValueError, match="estritamente crescente"):
        threshold_curve([1.0], [1.0], ["a"], (2.0, 2.0))
