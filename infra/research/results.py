"""Os resultados do moinho: o contraste e o relatório, ambos congelados.

Vivem à parte de `protocol.py` para que `verdict.py` e `report.py` os possam importar
sem ciclo — e para caber no orçamento de 350 linhas por módulo.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from infra.research.resampling import Interval
from infra.research.spec import PreRegistration
from infra.research.stats import Bucket, CurvePoint, Shape


@dataclass(frozen=True)
class Contrast:
    """Um contraste entre o braço selecionado e o resto, na unidade do desfecho."""

    label: str
    threshold: float
    n_selected: int
    n_rest: int
    mean_selected: float
    mean_rest: float
    d: float
    ci: Interval
    ci_block: Interval | None
    p_perm: float


@dataclass(frozen=True)
class Report:
    """Tudo o que o estudo produziu — os números, o veredito e o que os limita."""

    name: str
    origin: str
    fingerprint: str
    pre_registration: PreRegistration
    threshold: float
    minimum_effect: float
    cluster_column: str
    stratum_column: str | None
    n_rows: int
    n_used: int
    refused_by_guard: int
    censored_outcome: int
    censored_variable: int
    purged: int
    contrast: Contrast
    in_sample: Contrast | None
    out_of_sample: Contrast | None
    curve: tuple[CurvePoint, ...]
    shape: Shape
    buckets: tuple[Bucket, ...]
    money_total: Decimal | None
    verdict: str
    reasons: tuple[str, ...]
    caveats: tuple[str, ...]
    assumptions: tuple[str, ...]
