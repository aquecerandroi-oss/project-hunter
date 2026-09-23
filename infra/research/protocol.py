"""O moinho: uma hipótese entra, um veredito sai. `run_hypothesis(spec) -> Report`.

Protocolo congelado, destilado dos R65/R67/R68/R69:

1. **Pré-registo ou nada.** Sem previsão, refutação, regra de decisão, data e política
   de limiar, o moinho levanta `PreRegistrationError` antes de ler uma linha.
2. **Guarda anti-antecipação** sobre cada linha (`guards.py`), com os instantes de
   observabilidade declarados no spec — ou uma dispensa escrita, que vira ressalva.
3. **Censura declarada**: linha sem desfecho ou sem a variável sai da população e é
   contada. Ausente nunca é zero (o bug que o R69 apanhou).
4. **Contraste orientado**: `D = média(selecionados) − média(resto)`, com os
   selecionados já orientados pela direção, para a previsão ser sempre `D > 0`.
5. **IC por bootstrap de cluster** (mint/mercado) e, se declarado, **de blocos**
   (dia/hora); **p por permutação estratificada** dentro do estrato.
6. **Curva de limiares** e diagnóstico planalto-vs-pico.
7. **Veredito de três rótulos**, nunca "promissor".

Nada aqui abre socket nem lê relógio: `spec.loader` é a única fonte de dados e o
instante de decisão vem das próprias linhas.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

import numpy as np

from infra.research.guards import Instants, check_observable
from infra.research.guards import LookAheadError as LookAheadError
from infra.research.resampling import Interval
from infra.research.results import Contrast, Report
from infra.research.spec import (
    HypothesisSpec,
    ObservabilityColumns,
    Row,
    check_pre_registration,
    fingerprint,
)
from infra.research.stats import (
    block_bootstrap,
    bucket_table,
    cluster_bootstrap,
    contrast,
    permutation_p,
    plateau_or_spike,
    select,
    terciles,
    threshold_curve,
)
from infra.research.verdict import caveats, decide

# --------------------------------------------------------------------------- leitura


def _num(value: object) -> float | None:
    """Converte para float; ausente continua ausente (nunca vira zero).

    NaN e infinito contam como **ausente**: um NaN que atravessava daqui produzia
    `D = nan` e, com o IC a descartar as réplicas contaminadas, um `REFUTA` de mentira
    (contraexemplo da Astra, T4.87).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, int | float | Decimal):
        return _finite(float(value))
    text = str(value).strip()
    if text in ("", "None", "NULL"):
        return None
    if text in ("t", "true", "True"):
        return 1.0
    if text in ("f", "false", "False"):
        return 0.0
    try:
        return _finite(float(text))
    except ValueError:
        return None


def _finite(value: float) -> float | None:
    return value if math.isfinite(value) else None


def _guard(spec: HypothesisSpec, rows: Sequence[Mapping[str, object]]) -> tuple[list[Any], int]:
    obs = spec.observability
    if not isinstance(obs, ObservabilityColumns):
        return list(rows), 0
    kept: list[Mapping[str, object]] = []
    refused = 0
    for i, row in enumerate(rows):
        decision = row.get(spec.decision_instant)
        if not isinstance(decision, datetime):
            raise ValueError(f"linha {i}: {spec.decision_instant!r} não é datetime")
        inst = Instants(
            as_of=_dt(row, obs.as_of, i),
            computed_at=_dt(row, obs.computed_at, i),
            tape_as_of=None if obs.tape_as_of is None else _opt(row, obs.tape_as_of, i),
        )
        motive = check_observable(inst, decision, f"{spec.name} linha {i}", lag=obs.lag)
        if motive is None:
            kept.append(row)
        elif obs.strict:
            raise LookAheadError(f"{spec.name} linha {i}: {motive}")
        else:
            refused += 1
    return kept, refused


def _dt(row: Mapping[str, object], column: str, i: int) -> datetime:
    value = row.get(column)
    if not isinstance(value, datetime):
        raise ValueError(f"linha {i}: coluna {column!r} não é datetime")
    return value


def _opt(row: Mapping[str, object], column: str, i: int) -> datetime | None:
    """Coluna de instante **declarada** no spec: só `datetime` ou ausente.

    Devolver `None` em silêncio para uma string ISO desligava a checagem da fita — uma
    fita um dia no futuro passava como se a coluna não existisse (achado da Astra).
    """
    value = row.get(column)
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise ValueError(
            f"linha {i}: coluna de instante {column!r} não é datetime (é "
            f"{type(value).__name__}); converta no loader, a guarda não adivinha"
        )
    return value


# ------------------------------------------------------------------------- contraste


def _contrast(
    spec: HypothesisSpec,
    rows: Sequence[Mapping[str, object]],
    threshold: float,
    label: str,
    *,
    seed_shift: int = 0,
) -> Contrast:
    plan = spec.inference
    x = [_num(r.get(spec.variable)) for r in rows]
    y = np.array([float(_num(r.get(spec.outcome)) or 0.0) for r in rows])
    sel = select(x, threshold, spec.direction)
    ns, nr = int(sel.sum()), int((~sel).sum())
    if ns == 0 or nr == 0:
        empty = Interval(float("nan"), float("nan"), float("nan"), 0)
        return Contrast(
            label,
            threshold,
            ns,
            nr,
            float("nan"),
            float("nan"),
            float("nan"),
            empty,
            None,
            float("nan"),
        )
    ci = cluster_bootstrap(
        y, sel, [r.get(plan.cluster) for r in rows], reps=plan.reps, seed=plan.seed + seed_shift
    )
    ci_block = (
        block_bootstrap(
            y, sel, [r.get(plan.block) for r in rows], reps=plan.reps, seed=plan.seed + seed_shift
        )
        if plan.block
        else None
    )
    strata = [r.get(plan.stratum) for r in rows] if plan.stratum else None
    p = permutation_p(y, sel, strata, reps=plan.reps, seed=plan.seed + seed_shift)
    return Contrast(
        label,
        threshold,
        ns,
        nr,
        float(y[sel].mean()),
        float(y[~sel].mean()),
        contrast(y, sel),
        ci,
        ci_block,
        p,
    )


def _slice_by_split(
    spec: HypothesisSpec, rows: Sequence[Mapping[str, object]]
) -> tuple[list[Row] | None, list[Row] | None, list[Row], int]:
    """Devolve (treino, teste, purgadas) pela fronteira, com purga em valores distintos.

    A coluna do split tem de ser **texto** (rótulo de dia/período): comparar
    `datetime` com a string `train_until` ordena por texto e mete `2026-09-01 23:00+00`
    no treino de uma fronteira `2026-09-01T12:00:00Z` (contraexemplo da Astra). A purga
    é contada em **valores distintos da coluna**, logo a coluna tem de ser o período
    (dia), não o instante — `purge=60` sobre carimbos por segundo purga 60 segundos,
    não 60 minutos.
    """
    split = spec.split
    if split is None:
        return None, None, [], 0
    values = [r.get(split.column) for r in rows]
    bad = [type(v).__name__ for v in values if not isinstance(v, str)]
    if bad:
        raise ValueError(
            f"a coluna do split {split.column!r} tem de ser texto ordenável (rótulo de "
            f"dia/período); veio {sorted(set(bad))}. Converta no loader."
        )
    keys = sorted({str(v) for v in values})
    after = [k for k in keys if k > split.train_until]
    purged_keys = set(after[: split.purge])
    train = [r for r in rows if str(r.get(split.column)) <= split.train_until]
    test = [
        r
        for r in rows
        if str(r.get(split.column)) > split.train_until
        and str(r.get(split.column)) not in purged_keys
    ]
    purged_rows = [r for r in rows if str(r.get(split.column)) in purged_keys]
    return train, test, purged_rows, len(purged_rows)


# ------------------------------------------------------------------------- entrada


def run_hypothesis(spec: HypothesisSpec) -> Report:
    """Corre o protocolo congelado sobre a hipótese. Recusa sem pré-registo."""
    pre = check_pre_registration(spec)
    raw = list(spec.loader())
    kept, refused = _guard(spec, raw)
    with_outcome = [r for r in kept if _num(r.get(spec.outcome)) is not None]
    rows = [r for r in with_outcome if _num(r.get(spec.variable)) is not None]
    censored_outcome = len(kept) - len(with_outcome)
    censored_variable = len(with_outcome) - len(rows)

    pol, plan = spec.policy, spec.inference
    train, test, _purged_rows, purged = _slice_by_split(spec, rows)
    if spec.split is not None:
        # As linhas purgadas existem para separar treino de teste; deixá-las sustentar o
        # contraste principal tornava a purga decorativa (contraexemplo da Astra: 200 de
        # 202 linhas do efeito estavam na purga e o veredito continuava CONFIRMA).
        rows = (train or []) + (test or [])
    main = _contrast(spec, rows, pol.frozen_threshold, f"limiar congelado {pol.frozen_threshold:g}")
    x = [_num(r.get(spec.variable)) for r in rows]
    y = [float(_num(r.get(spec.outcome)) or 0.0) for r in rows]
    curve = threshold_curve(
        x,
        y,
        [r.get(plan.cluster) for r in rows],
        plan.thresholds,
        direction=spec.direction,
        min_per_side=pol.min_per_side,
        reps=plan.reps,
        seed=plan.seed,
    )
    shape = plateau_or_spike(curve)
    edges = terciles(x)
    buckets = tuple(bucket_table(x, y, list(edges))) if edges else ()

    in_sample = (
        _contrast(
            spec,
            train,
            pol.frozen_threshold,
            f"treino (até {spec.split.train_until})",
            seed_shift=101,
        )
        if train and spec.split
        else None
    )
    out_of_sample = (
        _contrast(
            spec,
            test,
            pol.frozen_threshold,
            f"teste (depois de {spec.split.train_until})",
            seed_shift=202,
        )
        if test and spec.split
        else None
    )

    verdict, reasons = decide(spec, main, shape, out_of_sample, has_split=spec.split is not None)
    bits = {
        "contrast": main,
        "n_rows": len(raw),
        "refused_by_guard": refused,
        "censored_outcome": censored_outcome,
        "censored_variable": censored_variable,
        "n_used": len(rows),
        "purged": purged,
    }
    money = (
        sum((Decimal(str(r.get(spec.money_column))) for r in rows), Decimal(0))
        if spec.money_column
        else None
    )
    return Report(
        name=spec.name,
        origin=spec.origin,
        fingerprint=fingerprint(spec),
        pre_registration=pre,
        threshold=pol.frozen_threshold,
        minimum_effect=pol.minimum_effect,
        cluster_column=plan.cluster,
        stratum_column=plan.stratum,
        n_rows=len(raw),
        n_used=len(rows),
        refused_by_guard=refused,
        censored_outcome=censored_outcome,
        censored_variable=censored_variable,
        purged=purged,
        contrast=main,
        in_sample=in_sample,
        out_of_sample=out_of_sample,
        curve=tuple(curve),
        shape=shape,
        buckets=buckets,
        money_total=money,
        verdict=verdict,
        reasons=tuple(reasons),
        caveats=caveats(spec, bits),
        assumptions=tuple(spec.assumptions),
    )
