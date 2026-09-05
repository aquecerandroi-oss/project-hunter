"""The strategy registry: ``(key, version) -> Strategy``.

A version is an experiment (SHADOW-LAB.md §1), so the registry is deliberately
dumb: it never picks "the latest", never falls back to another version, and
refuses to register the same ``(key, version)`` twice. Resolving a signal's
``strategy_version`` to code has to be exact, or a run would be attributed to the
wrong frozen parameters.
"""

from __future__ import annotations

from collections.abc import Iterable

from hunter_core.strategies.base import Strategy
from hunter_core.strategies.momentum_v1 import MOMENTUM_V1
from hunter_core.strategies.volume_anomaly_v1 import VOLUME_ANOMALY_V1


class StrategyRegistry:
    """An immutable-by-convention map of the strategies this build knows."""

    def __init__(self, strategies: Iterable[Strategy] = ()) -> None:
        self._by_id: dict[tuple[str, str], Strategy] = {}
        for strategy in strategies:
            self.register(strategy)

    def register(self, strategy: Strategy) -> None:
        identity = (strategy.key, strategy.version)
        if identity in self._by_id:
            raise ValueError(f"{identity[0]} {identity[1]} is already registered")
        self._by_id[identity] = strategy

    def get(self, key: str, version: str) -> Strategy:
        """The strategy registered as ``(key, version)``; ``KeyError`` if there is none."""
        try:
            return self._by_id[(key, version)]
        except KeyError:
            raise KeyError(f"no strategy registered as {key} {version}") from None

    def all(self) -> tuple[Strategy, ...]:
        """Every registered strategy, ordered by ``(key, version)``."""
        return tuple(self._by_id[identity] for identity in sorted(self._by_id))


DEFAULT_REGISTRY = StrategyRegistry((MOMENTUM_V1, VOLUME_ANOMALY_V1))
"""The v0 Shadow Lab roster. LONG only, ``research_only`` (SHADOW-LAB.md §10)."""
