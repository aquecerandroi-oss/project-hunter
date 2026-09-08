"""Protocolo de replicação — estatística pura (`docs/plans/REPLICATION.md`).

Uma versão *promissora* (o placar disse `validada` uma vez) só é considerada
**real** quando quatro repetições independentes concordam: fora da amostra no
tempo, dez irmãs de parâmetro, as duas metades de mercado e o bootstrap. Aqui
mora a parte pura — sem IO, sem relógio, sem banco: quem lê o Postgres é
``hunter_strategy_worker.replication_stats``, quem deriva as irmãs é
``infra/scripts/replicate_strategy_version.py``.

Nada neste pacote ativa, promove ou aproxima uma versão da carteira.
"""

from hunter_indicators.replication.bootstrap import (
    BootstrapResult,
    SignTestResult,
    bootstrap_mean_ci,
    cluster_bootstrap_mean_ci,
    sign_test,
)
from hunter_indicators.replication.jitter import (
    JITTER_PCT,
    JitterChange,
    JitterResult,
    jitter_parameters,
)
from hunter_indicators.replication.protocol import (
    SIBLINGS_N,
    SIBLINGS_REQUIRED,
    STATUS_NONE,
    STATUS_PROMISING,
    STATUS_REAL,
    STATUS_REFUTED,
    STATUS_REPLICATING,
    Block,
    ReplicationReport,
    SiblingArm,
    replication_report,
)
from hunter_indicators.replication.split import (
    MIN_MARKETS_PER_HALF,
    MIN_OUTCOMES_PER_HALF,
    HalfStats,
    HalvesResult,
    market_half,
    split_by_market,
)
from hunter_indicators.replication.stats import (
    MATURITY_DAYS,
    MATURITY_HALF_DAYS,
    MATURITY_HALF_OUTCOMES,
    MATURITY_OUTCOMES,
    PF_NO_LOSSES,
    PF_NO_SAMPLE,
    Outcome,
    PopulationStats,
    after,
    dedupe_outcomes,
    profit_factor_passes,
    scoreboard_verdict,
    verdict_from_values,
)

__all__ = [
    "JITTER_PCT",
    "MATURITY_DAYS",
    "MATURITY_HALF_DAYS",
    "MATURITY_HALF_OUTCOMES",
    "MATURITY_OUTCOMES",
    "PF_NO_LOSSES",
    "PF_NO_SAMPLE",
    "MIN_MARKETS_PER_HALF",
    "MIN_OUTCOMES_PER_HALF",
    "SIBLINGS_N",
    "SIBLINGS_REQUIRED",
    "STATUS_NONE",
    "STATUS_PROMISING",
    "STATUS_REAL",
    "STATUS_REFUTED",
    "STATUS_REPLICATING",
    "Block",
    "BootstrapResult",
    "HalfStats",
    "HalvesResult",
    "JitterChange",
    "JitterResult",
    "Outcome",
    "PopulationStats",
    "ReplicationReport",
    "SiblingArm",
    "SignTestResult",
    "after",
    "bootstrap_mean_ci",
    "cluster_bootstrap_mean_ci",
    "dedupe_outcomes",
    "jitter_parameters",
    "market_half",
    "profit_factor_passes",
    "replication_report",
    "scoreboard_verdict",
    "sign_test",
    "split_by_market",
    "verdict_from_values",
]
