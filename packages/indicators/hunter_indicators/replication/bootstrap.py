"""Bootstrap do bloco 4 do protocolo de replicação (`docs/plans/REPLICATION.md` §3.4).

Duas reamostragens e um teste de sinal, todos puros e semeados:

- :func:`bootstrap_mean_ci` — percentil i.i.d. sobre os R líquidos avaliáveis;
- :func:`cluster_bootstrap_mean_ci` — reamostra **dias inteiros**, porque rótulos
  de três barreiras se sobrepõem no tempo e mercados simultâneos são dependentes
  (KB-0051; SHADOW-LAB.md §9 pede reamostragem em blocos de tempo). O intervalo
  i.i.d. é sempre o mais estreito dos dois, e reportar só ele seria vender
  precisão que a amostra não tem;
- :func:`sign_test` — binomial exata bicaudal, **reportada e não decisória**:
  "ganha mais vezes" e "ganha mais dinheiro" são perguntas diferentes (KB-0046).

Abaixo de :data:`MIN_SAMPLE` a função **recusa com motivo** em vez de devolver um
intervalo: um percentil de 1 000 reamostras sobre 12 observações é ruído sobre
ruído, e um número devolvido é um número que alguém vai citar.

Precisão: a estatística roda em ``float64`` (NumPy, janelas em memória — regra
de numéricos do projeto) e **sai** em ``Decimal`` quantizado em quatro casas,
que é a forma como todo R viaja no Lab. Nada aqui é dinheiro persistido.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import numpy as np

__all__ = [
    "CHUNK",
    "CONFIDENCE",
    "MIN_SAMPLE",
    "RESAMPLES",
    "SIGN_EXACT_MAX",
    "BootstrapResult",
    "SignTestResult",
    "bootstrap_mean_ci",
    "cluster_bootstrap_mean_ci",
    "sign_test",
]

MIN_SAMPLE = 30
"""``BOOTSTRAP_N_MIN`` do protocolo: abaixo disso o bloco recusa (nunca refuta)."""

RESAMPLES = 1000
"""``BOOTSTRAP_REAMOSTRAS``."""

CONFIDENCE = Decimal("0.95")
"""``BOOTSTRAP_CONFIANCA`` — intervalo percentil bicaudal da média."""

CHUNK = 250
"""Reamostras por lote. 1 000 × n em memória de uma vez é 40 MB com n = 5 000;
em lotes o pico não depende do tamanho da população."""

SIGN_EXACT_MAX = 2000
"""Acima disso o teste de sinal usa a aproximação normal com correção de
continuidade em vez da soma binomial exata (a soma exata com ``math.comb`` em
n = 20 000 custa mais do que a precisão que ela ganha)."""

_FOUR = Decimal("0.0001")


def _quantize(value: float) -> Decimal:
    return Decimal(repr(value)).quantize(_FOUR, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    """Um intervalo percentil da média, ou a recusa que o substitui."""

    n: int
    mean: Decimal | None
    ci_low: Decimal | None
    ci_high: Decimal | None
    resamples: int
    seed: int
    confidence: Decimal
    method: str
    """``iid_percentile_v1`` ou ``day_cluster_percentile_v1``. Mudar a fórmula é
    um método novo, nunca uma edição do antigo (SHADOW-LAB.md §1)."""

    refused_reason: str | None = None
    groups: int | None = None
    """Dias distintos reamostrados (só no método por blocos)."""

    @property
    def ok(self) -> bool:
        return self.refused_reason is None

    @property
    def excludes_zero(self) -> bool:
        """Os dois extremos do mesmo lado de zero. Recusa nunca "exclui zero"."""
        if not self.ok or self.ci_low is None or self.ci_high is None:
            return False
        return self.ci_low > 0 or self.ci_high < 0

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "mean": None if self.mean is None else str(self.mean),
            "ci_low": None if self.ci_low is None else str(self.ci_low),
            "ci_high": None if self.ci_high is None else str(self.ci_high),
            "resamples": self.resamples,
            "seed": self.seed,
            "confidence": str(self.confidence),
            "method": self.method,
            "groups": self.groups,
            "refused_reason": self.refused_reason,
        }


def _refusal(n: int, seed: int, method: str, reason: str) -> BootstrapResult:
    return BootstrapResult(
        n=n,
        mean=None,
        ci_low=None,
        ci_high=None,
        resamples=0,
        seed=seed,
        confidence=CONFIDENCE,
        method=method,
        refused_reason=reason,
    )


def _generator(seed: int) -> np.random.Generator:
    """PCG64 explícito: o fluxo tem de ser o mesmo em qualquer máquina que releia
    o relatório com a mesma semente (a semente vai no evento de auditoria)."""
    return np.random.Generator(np.random.PCG64(seed))


def _percentiles(means: np.ndarray[Any, Any], confidence: Decimal) -> tuple[float, float]:
    alpha = float(1 - confidence)
    low, high = np.quantile(means, [alpha / 2, 1 - alpha / 2], method="linear")
    return float(low), float(high)


def bootstrap_mean_ci(
    values: Sequence[Decimal],
    *,
    seed: int,
    resamples: int = RESAMPLES,
    confidence: Decimal = CONFIDENCE,
    min_sample: int = MIN_SAMPLE,
) -> BootstrapResult:
    """Intervalo percentil da média por reamostragem com reposição (i.i.d.).

    ``amostra_insuficiente`` quando ``n < min_sample`` — com o número na mensagem,
    porque "recusou" sem "quanto falta" não é um motivo, é um silêncio.
    """
    n = len(values)
    if n < min_sample:
        return _refusal(n, seed, "iid_percentile_v1", f"amostra_insuficiente: {n} < {min_sample}")
    sample = np.asarray([float(value) for value in values], dtype=np.float64)
    rng = _generator(seed)
    means = np.empty(resamples, dtype=np.float64)
    done = 0
    while done < resamples:
        size = min(CHUNK, resamples - done)
        draws = rng.integers(0, n, size=(size, n))
        means[done : done + size] = sample[draws].mean(axis=1)
        done += size
    low, high = _percentiles(means, confidence)
    return BootstrapResult(
        n=n,
        mean=_quantize(float(sample.mean())),
        ci_low=_quantize(low),
        ci_high=_quantize(high),
        resamples=resamples,
        seed=seed,
        confidence=confidence,
        method="iid_percentile_v1",
    )


def cluster_bootstrap_mean_ci(
    values: Sequence[Decimal],
    groups: Sequence[object],
    *,
    seed: int,
    resamples: int = RESAMPLES,
    confidence: Decimal = CONFIDENCE,
    min_sample: int = MIN_SAMPLE,
    min_groups: int = 5,
) -> BootstrapResult:
    """Intervalo percentil da média reamostrando **grupos inteiros** (dias).

    A média de uma reamostra é a média da concatenação dos dias sorteados —
    calculada por somas e contagens por dia, que é a mesma conta sem materializar
    a concatenação. Dias com mais observações pesam mais, exatamente como pesam
    na população real.
    """
    if len(values) != len(groups):
        raise ValueError("values e groups precisam ter o mesmo comprimento")
    n = len(values)
    method = "day_cluster_percentile_v1"
    if n < min_sample:
        return _refusal(n, seed, method, f"amostra_insuficiente: {n} < {min_sample}")
    keys = sorted({str(group) for group in groups})
    if len(keys) < min_groups:
        return _refusal(n, seed, method, f"grupos_insuficientes: {len(keys)} < {min_groups}")
    index = {key: position for position, key in enumerate(keys)}
    sums = np.zeros(len(keys), dtype=np.float64)
    counts = np.zeros(len(keys), dtype=np.float64)
    for value, group in zip(values, groups, strict=True):
        position = index[str(group)]
        sums[position] += float(value)
        counts[position] += 1.0
    rng = _generator(seed)
    means = np.empty(resamples, dtype=np.float64)
    done = 0
    while done < resamples:
        size = min(CHUNK, resamples - done)
        draws = rng.integers(0, len(keys), size=(size, len(keys)))
        means[done : done + size] = sums[draws].sum(axis=1) / counts[draws].sum(axis=1)
        done += size
    low, high = _percentiles(means, confidence)
    return BootstrapResult(
        n=n,
        mean=_quantize(float(sums.sum() / counts.sum())),
        ci_low=_quantize(low),
        ci_high=_quantize(high),
        resamples=resamples,
        seed=seed,
        confidence=confidence,
        method=method,
        groups=len(keys),
    )


@dataclass(frozen=True, slots=True)
class SignTestResult:
    """Positivos contra negativos, com a p bicaudal exata sob p = 1/2."""

    positives: int
    negatives: int
    zeros: int
    p_value: Decimal | None
    method: str
    refused_reason: str | None = None

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "positives": self.positives,
            "negatives": self.negatives,
            "zeros": self.zeros,
            "p_sign": None if self.p_value is None else str(self.p_value),
            "method": self.method,
            "refused_reason": self.refused_reason,
        }


def _exact_two_sided(successes: int, trials: int) -> float:
    tail = sum(math.comb(trials, k) for k in range(min(successes, trials - successes) + 1))
    return min(1.0, 2.0 * tail / float(2**trials))


def _normal_two_sided(successes: int, trials: int) -> float:
    mean, sigma = trials / 2.0, math.sqrt(trials) / 2.0
    z = (abs(successes - mean) - 0.5) / sigma
    return min(1.0, math.erfc(z / math.sqrt(2.0)))


def sign_test(values: Sequence[Decimal]) -> SignTestResult:
    """Teste de sinal bicaudal sobre os R; zeros exatos são **excluídos**.

    Excluir os zeros é a convenção clássica do teste (um empate não é evidência
    para nenhum lado) e está declarada aqui porque muda o denominador.
    """
    positives = sum(1 for value in values if value > 0)
    negatives = sum(1 for value in values if value < 0)
    zeros = len(values) - positives - negatives
    trials = positives + negatives
    if trials == 0:
        return SignTestResult(0, 0, zeros, None, "exact_binomial_v1", "sem_amostra_com_sinal")
    if trials <= SIGN_EXACT_MAX:
        p_value, method = _exact_two_sided(positives, trials), "exact_binomial_v1"
    else:
        p_value, method = _normal_two_sided(positives, trials), "normal_approx_v1"
    return SignTestResult(positives, negatives, zeros, _quantize(p_value), method)
