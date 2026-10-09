"""The copy lane's rule set (H-037, EXP-M28, decision 2026-10-09 "piloto de copiar carteiras no papel"):
``copy_v0/1``, a ``research_only`` set whose ``params.clock = 'copy'`` marks it as this lane's own, the way
``launch_lane_repo.py`` marks ``clock = 'event'``. The parameter names and values are the ones frozen in
``EXP-M28`` ("Parâmetros congelados"; ``docs/design/copiar-carteiras-papel.md`` §3) — the seed reads
the same JSON.

Frozen at T0: the leader list, the ticket and the exits are read **once** when the lane starts
(``copy_lane.run_copy_lane_forever`` restarts it when a different set becomes the active one);
nothing here is a hot-path read.

``params`` (decimals are JSON strings, counts and switches bare JSON, like every other set):

* ``leaders``: ``[{"wallet": "...", "stratum": "regra"}, ...]`` — the frozen follow list;
* ``size_sol`` 0.05 · ``min_trigger_sol`` 0.1 (what the leader spent, from its own SOL leg);
* ``exit_leader_drop_fraction`` 0.5 (sell when the leader's position is at or below this share of its
  peak, or 0) · ``stop_fraction`` 0.5 (our own stop: mark at or below this share of the cost) ·
  ``time_cap_s`` 3600;
* ``exec_latency_s`` 1.65 — the declared latency between our decision and the market state the paper
  fill is priced on; ``fill_window_s`` 30 / ``exit_window_s`` 60 — how long a price read may keep retrying;
* ``max_attempts_per_leader_day`` 20 · ``max_open_per_stratum`` 100 (open copies **plus** attempts
  still waiting for a price);
* ``horizon_days`` 30 (emenda 4) — entries stop at T0 + this; what is open matures after;
* ``stratum``: the set's identity (``regra`` is the primary). Optional when the leaders all share one
  stratum; **required when ``leaders`` is empty** — ``escolha_everton`` may be seeded with no leader
  at all (emenda 4 d) and must still be known as the secondary, never mistaken for the primary;
* ``fee_pct`` 1.25 and ``priority_fee_sol`` 0.00005, per leg;
* ``venues``: ``["curve"]`` (or with ``"pumpswap"`` once the pool-buy acceptance P exists — the lane
  never prices a pool *buy*, so a mint already on the pool is ``fora_de_praca`` whatever this says);
* the lane's own, not part of the pre-registered economics: ``act_on_unconfirmed`` (decide on the first
  trustworthy signal — Everton's milliseconds), ``confirm_timeout_s`` 30, ``mark_every_s`` 5,
  ``queue_max`` 1000.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_meme_worker.lab_params import decimal_of, switch_of

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "COPY_CLOCK",
    "PRIMARY_STRATUM",
    "CopyLeader",
    "CopySpec",
    "load_copy_specs",
]

COPY_CLOCK = "copy"
PRIMARY_STRATUM = "regra"
"""The stratum of the cohort's only population (``copy_v0/1``); ``escolha_everton`` is descriptive."""
LAMPORTS_PER_SOL = Decimal(1_000_000_000)
ONE = Decimal(1)

_LOAD = text(
    "SELECT id, name, version, kind, exp_ref, status, params FROM meme_rule_sets "
    "WHERE kind = 'research_only' AND params ->> 'clock' = :clock "
    "  AND (status = 'active' OR EXISTS (SELECT 1 FROM meme_paper_bets b "
    "       WHERE b.rule_set_id = meme_rule_sets.id AND b.status = 'open')) "
    "ORDER BY name, version"
)


@dataclass(frozen=True, slots=True)
class CopyLeader:
    wallet: str
    stratum: str


def _count(params: Mapping[str, Any], name: str, default: int) -> int:
    value = params.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TypeError(f"{name} is a count: a bare non-negative JSON integer, never {value!r}")
    return value


def _fraction(params: Mapping[str, Any], name: str) -> Decimal:
    value = decimal_of(params[name])
    if not 0 < value < ONE:
        raise ValueError(f"{name} must be a fraction in (0, 1), never {value}")
    return value


@dataclass(frozen=True, slots=True)
class CopySpec:
    id: str
    name: str
    version: str
    leaders: tuple[CopyLeader, ...]
    size_sol: Decimal
    min_trigger_sol: Decimal
    exit_leader_drop_fraction: Decimal
    stop_fraction: Decimal
    time_cap_s: int
    exec_latency_s: Decimal
    fill_window_s: int
    exit_window_s: int
    max_attempts_per_leader_day: int
    max_open_per_stratum: int
    horizon_days: int
    stratum: str
    status: str
    fee_pct: Decimal
    priority_fee_sol: Decimal
    venues: tuple[str, ...]
    act_on_unconfirmed: bool
    confirm_timeout_s: int
    mark_every_s: int
    queue_max: int

    @property
    def label(self) -> str:
        return f"{self.name}/{self.version}"

    @property
    def is_primary(self) -> bool:
        """The set whose copies are the pre-registered population: it keeps protected priority."""
        return self.stratum == PRIMARY_STRATUM

    @property
    def accepting_entries(self) -> bool:
        """A retired set that still holds open copies is only *kept* (exits, marks, time cap)."""
        return self.status == "active"

    @property
    def wallets(self) -> frozenset[str]:
        return frozenset(leader.wallet for leader in self.leaders)

    @property
    def execution_latency_ms(self) -> int:
        return int(self.exec_latency_s * 1000)

    @property
    def min_trigger_lamports(self) -> int:
        return int(self.min_trigger_sol * LAMPORTS_PER_SOL)

    @classmethod
    def from_params(
        cls, *, id: str, name: str, version: str, params: Mapping[str, Any], status: str = "active"
    ) -> CopySpec:
        leaders = tuple(
            CopyLeader(wallet=str(row["wallet"]), stratum=str(row["stratum"]))
            for row in params["leaders"]
        )
        strata = {leader.stratum for leader in leaders}
        stratum = params.get("stratum") or (next(iter(strata)) if len(strata) == 1 else None)
        if stratum is None:
            raise ValueError(
                f"{name}/{version}: name the set's stratum (leaders mix {sorted(strata)})"
            )
        if any(s != stratum for s in strata):
            raise ValueError(f"{name}/{version}: a leader outside the set's stratum {stratum!r}")
        if len({leader.wallet for leader in leaders}) != len(leaders):
            raise ValueError(f"{name}/{version} lists a leader twice")
        size = decimal_of(params["size_sol"])
        floor = decimal_of(params["min_trigger_sol"])
        latency = decimal_of(params["exec_latency_s"])
        venues = tuple(str(v) for v in params.get("venues", ["curve"]))
        if size <= 0 or floor < 0 or latency < 0:
            raise ValueError(
                f"{name}/{version}: size must be positive, floor and latency not negative"
            )
        if "curve" not in venues:
            raise ValueError(f"{name}/{version}: the curve is always a venue")
        return cls(
            id=str(id),
            name=name,
            version=version,
            leaders=leaders,
            size_sol=size,
            min_trigger_sol=floor,
            exit_leader_drop_fraction=_fraction(params, "exit_leader_drop_fraction"),
            stop_fraction=_fraction(params, "stop_fraction"),
            time_cap_s=_count(params, "time_cap_s", 3600),
            exec_latency_s=latency,
            fill_window_s=_count(params, "fill_window_s", 30),
            exit_window_s=_count(params, "exit_window_s", 60),
            max_attempts_per_leader_day=_count(params, "max_attempts_per_leader_day", 20),
            max_open_per_stratum=_count(params, "max_open_per_stratum", 100),
            horizon_days=_count(params, "horizon_days", 30),
            stratum=str(stratum),
            status=status,
            fee_pct=decimal_of(params.get("fee_pct", "1.25")),
            priority_fee_sol=decimal_of(params.get("priority_fee_sol", "0.00005")),
            venues=venues,
            act_on_unconfirmed=switch_of(params, "act_on_unconfirmed", True),
            confirm_timeout_s=_count(params, "confirm_timeout_s", 30),
            mark_every_s=max(1, _count(params, "mark_every_s", 5)),
            queue_max=max(1, _count(params, "queue_max", 1000)),
        )


async def load_copy_specs(session: AsyncSession) -> list[CopySpec]:
    """Every active ``clock = 'copy'`` rule set — ``copy_v0/1`` (stratum ``regra``, the primary) and
    ``copy_everton_v0/1`` (``escolha_everton``, descriptive). Empty = the lane stays inert."""
    rows = (await session.execute(_LOAD, {"clock": COPY_CLOCK})).mappings().all()
    return [
        CopySpec.from_params(
            id=str(r["id"]),
            name=r["name"],
            version=r["version"],
            params=r["params"],
            status=str(r["status"]),
        )
        for r in rows
    ]
