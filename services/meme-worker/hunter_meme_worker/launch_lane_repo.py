"""The launch lane's own rule sets (T4.67a): loaded straight from
``meme_rule_sets``, never through ``RuleSetSpec.from_params`` (T4.5's engine),
whose required keys — ``gate_key``, ``min_age_s``, ``target_x``... — describe
a curve this lane never reads. ``params.clock = 'event'`` is what marks a row
as this lane's own (:data:`~hunter_meme_worker.lab_models.CLOCKS` never
lists it, so the 15-second/minute engines skip it by construction).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_indicators.meme.launch_lane import LaunchGate
from hunter_meme_worker.lab_params import decimal_of

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "LAUNCH_CLOCK",
    "LAUNCH_GATE_KEY",
    "LAUNCH_GATE_VERSION",
    "LaunchRuleSpec",
    "load_launch_specs",
]

LAUNCH_CLOCK = "event"
LAUNCH_GATE_KEY = "pista_de_lancamento"
LAUNCH_GATE_VERSION = 1

_LOAD = text(
    "SELECT id, name, version, kind, exp_ref, status, params FROM meme_rule_sets "
    "WHERE status = 'active' AND params ->> 'clock' = :clock ORDER BY name, version"
)


@dataclass(frozen=True, slots=True)
class LaunchRuleSpec:
    """One ``meme_rule_sets`` row of the launch lane's own shape."""

    id: str
    name: str
    version: str
    kind: str
    exp_ref: str | None
    status: str
    size_sol: Decimal
    max_creator_initial_sol: Decimal
    exit_key: str
    time_stop_s: int
    exit_on_first_third_party_sell: bool
    max_drawdown_from_peak_pct: Decimal

    @property
    def label(self) -> str:
        return f"{self.name}/{self.version}"

    @property
    def gate(self) -> LaunchGate:
        return LaunchGate(
            key=LAUNCH_GATE_KEY,
            version=LAUNCH_GATE_VERSION,
            max_creator_initial_sol=self.max_creator_initial_sol,
        )

    @classmethod
    def from_params(
        cls,
        *,
        id: str,
        name: str,
        version: str,
        kind: str,
        exp_ref: str | None,
        status: str,
        params: Mapping[str, Any],
    ) -> LaunchRuleSpec:
        clock = str(params.get("clock", LAUNCH_CLOCK))
        if clock != LAUNCH_CLOCK:
            raise ValueError(f"{name}/{version} is not a launch-lane set (clock={clock!r})")
        return cls(
            id=str(id),
            name=name,
            version=version,
            kind=kind,
            exp_ref=exp_ref,
            status=status,
            size_sol=decimal_of(params["size_sol"]),
            max_creator_initial_sol=decimal_of(params["max_creator_initial_sol"]),
            exit_key=str(params["exit_key"]),
            time_stop_s=int(params["time_stop_s"]),
            exit_on_first_third_party_sell=bool(params.get("exit_on_first_third_party_sell", True)),
            max_drawdown_from_peak_pct=decimal_of(params["max_drawdown_from_peak_pct"]),
        )


async def load_launch_specs(session: AsyncSession) -> list[LaunchRuleSpec]:
    """Every active ``clock = 'event'`` set — ``hunter_worker`` already has
    ``SELECT`` on ``meme_rule_sets`` (``docs/DATABASE.md`` §38's own table)."""
    rows = (await session.execute(_LOAD, {"clock": LAUNCH_CLOCK})).mappings().all()
    return [
        LaunchRuleSpec.from_params(
            id=r["id"],
            name=r["name"],
            version=r["version"],
            kind=r["kind"],
            exp_ref=r["exp_ref"],
            status=r["status"],
            params=r["params"],
        )
        for r in rows
    ]
