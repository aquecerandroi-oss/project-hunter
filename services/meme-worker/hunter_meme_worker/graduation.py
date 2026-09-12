"""What "graduated" means to this radar (T4.2d) — four separate signals, one
reducer, and the denominator of progress with its provenance. Pure, plus the
small cache that reads ``/global-params`` once an hour.

The plantão's run 5 (12/09 05:51 BRT) measured that the REST ``complete = true``
is **not** a graduation: of 140 "complete" coins, 77 had ``real_sol_reserves =
0`` (47 Mayhem, market cap median US$ 9,57) and 72 were not on the site's
``graduated`` board — and 31 of the 68 that *were* on it also showed a zero
reserve, because a migrated curve's SOL has left for the pool. Astra's
must-fixes 1–2: keep the indicators separate, and a zero reserve classifies
nothing. So ``meme_tokens`` carries four stamps —

- ``rest_complete_seen_at``: the first REST/RPC photo with ``complete = true``;
- ``curve_filled_seen_at``: the first photo with ``real_sol_reserves`` at or
  above the fill threshold, **derived** from the ``/global-params`` record in
  force at the coin's creation (:func:`fill_threshold_sol`), never typed;
- ``graduated_board_seen_at``: the first presence on the site's ``graduated``
  board (``boards.py``);
- ``pool_created_at`` + ``pool_created_source``: the indexer's ``gd`` or the
  PumpPortal ``migrate`` frame, whichever this radar saw first —

and ``completed_at`` is :func:`earliest_completion` of them, with the one
declared exception: a REST ``complete`` whose photo carried no SOL does not
count on its own, and does not even lend its instant.

**The denominator.** ``curve_progress_pct = 1 − real/initial`` needs
``initial_real_token_reserves``. Until T4.2d it was written only from a virgin
photo (``real_sol_reserves = 0``), so a coin discovered after its first buy
never got one — 117/123 gate rows were ``progress_unknown`` in production at
06:04 BRT. Now a **standard** curve seen mid-life takes the record's initial
(``global_params``); a virgin photo still wins (``observed_virgin``), because
it is an observation of *this* curve. **Mayhem takes the same record, but only
through the chain** (T4.2e): the coin's agent is minted its own billion beside
the curve's supply and sells it *net* into the curve — the by-mint fixture of
T4.1 (``2sduGq…``, ``mayhem_state = paused``) holds 822 644 036,902123 real
tokens = 793 100 000 + 29 544 036,902123 of the agent's net sells, to the
subunit (``hunter_exchanges.pumpfun.mayhem_state``). So a Mayhem photo alone
claims nothing — neither ``observed_virgin`` (a reserve seen at
``real_sol = 0`` may hold the agent's tokens, not the initial: that fixture
sat at 1 lamport) nor the record — and :func:`mayhem_denominator` writes the
record once the ``MayhemState`` read reconciled and ``real − agent_net_sold ≤
initial`` (the humans hold a non-negative net), labelled ``mayhem_state``.
The record's fill threshold is not claimed for a Mayhem curve either:
``set_mayhem_virtual_params`` moves its virtual SOL (0,46–27,9 SOL on five
live curves against the record's 30), so the SOL a full Mayhem curve holds is
not the record's number.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol

from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.board_models import BOARDS_REST_SOURCE, RISK_SOURCE, TRENCHES_SOURCE
from hunter_exchanges.pumpfun.curve import raw_lamports_to_sol, raw_subunits_to_tokens
from hunter_exchanges.pumpfun.quote import GlobalParams, curve_fill_threshold_lamports

if TYPE_CHECKING:
    from hunter_exchanges.pumpfun.mayhem_state import NormalizedMayhemFlow
    from hunter_exchanges.pumpfun.models import NormalizedCurveState

logger = get_logger(__name__)

OBSERVED_VIRGIN = "observed_virgin"
GLOBAL_PARAMS = "global_params"
MAYHEM_STATE = "mayhem_state"
DENOMINATOR_UNKNOWN = "unknown"
"""``progress_denominator_source``: the three the worker writes (``0025``), and
the word the API renders for ``NULL`` (an unknown denominator has no source,
and the column is ``NULL`` for the same reason every unknown in ``meme_tokens``
is)."""

POOL_SOURCE_PUMPPORTAL = "pumpportal_ws"
POOL_SOURCE_TRENCHES = TRENCHES_SOURCE
POOL_SOURCE_INDEXER_BOARDS = BOARDS_REST_SOURCE
POOL_SOURCE_INDEXER_RISK = RISK_SOURCE
POOL_SOURCES: tuple[str, ...] = (
    POOL_SOURCE_PUMPPORTAL,
    POOL_SOURCE_TRENCHES,
    POOL_SOURCE_INDEXER_BOARDS,
    POOL_SOURCE_INDEXER_RISK,
)
"""``pool_created_source``: who reported the pool first — the PumpPortal
``migrate`` frame, or the indexer's ``gd`` on a board (socket or REST twin) or
on the risk read. The same list the database freezes in ``0024``."""


@dataclass(frozen=True, slots=True)
class CompletionSignals:
    """What one observation says about the four stamps. Unknown stays ``None``."""

    rest_complete_seen_at: datetime | None = None
    rest_reserve_is_zero: bool = False
    """The photo that said ``complete`` carried ``real_sol_reserves = 0`` — a
    Mayhem coin nobody bought, or a migrated curve whose SOL already left. It
    is recorded as the signal it is; it classifies nothing by itself."""
    curve_filled_seen_at: datetime | None = None
    graduated_board_seen_at: datetime | None = None
    pool_created_at: datetime | None = None
    pool_created_source: str | None = None


def earliest_completion(signals: CompletionSignals) -> datetime | None:
    """The reducer: the earliest of the four, minus the zero-reserve exception."""
    candidates = [
        signals.curve_filled_seen_at,
        signals.graduated_board_seen_at,
        signals.pool_created_at,
    ]
    if signals.rest_complete_seen_at is not None and not signals.rest_reserve_is_zero:
        candidates.append(signals.rest_complete_seen_at)
    present = [at for at in candidates if at is not None]
    return min(present) if present else None


def fill_threshold_sol(params: GlobalParams) -> Decimal:
    """``curve_fill_threshold_lamports`` in SOL — 85,005359057 for the 2025-07-18 record."""
    return raw_lamports_to_sol(curve_fill_threshold_lamports(params))


def is_mayhem(state: NormalizedCurveState) -> bool:
    """The photo says Mayhem: the on-chain flag, or the site's agent state."""
    return state.mayhem_enabled is True or state.mayhem_state is not None


def curve_signals(state: NormalizedCurveState, params: GlobalParams | None) -> CompletionSignals:
    """The two REST-side signals of one photo. No record, no threshold, no claim —
    and no fill claim for a Mayhem curve, whose virtual SOL the agent moves."""
    filled = (
        params is not None
        and not is_mayhem(state)
        and state.real_sol_reserves >= fill_threshold_sol(params)
    )
    return CompletionSignals(
        rest_complete_seen_at=state.observed_at if state.complete else None,
        rest_reserve_is_zero=state.real_sol_reserves == 0,
        curve_filled_seen_at=state.observed_at if filled else None,
    )


@dataclass(frozen=True, slots=True)
class Denominator:
    value: Decimal | None
    source: str | None
    """``observed_virgin`` | ``global_params`` | ``mayhem_state`` | ``None``
    (unknown, nothing to write)."""


UNKNOWN = Denominator(None, None)


def denominator_for(state: NormalizedCurveState, params: GlobalParams | None) -> Denominator:
    """What this photo lets the row claim as ``initial_real_token_reserves``.

    A Mayhem photo claims nothing here: its reserve may carry the agent's own
    tokens (module docstring), so the record is written only by
    :func:`mayhem_denominator`, after the chain reconciled the agent's flow.
    """
    if is_mayhem(state):
        return UNKNOWN
    if state.real_sol_reserves == 0 and not state.complete:
        return Denominator(state.real_token_reserves, OBSERVED_VIRGIN)
    if params is None:
        return UNKNOWN
    initial = raw_subunits_to_tokens(params.initial_real_token_reserves)
    if state.real_token_reserves > initial:
        return UNKNOWN  # holds more than the record's initial: not its curve
    return Denominator(initial, GLOBAL_PARAMS)


def mayhem_denominator(flow: NormalizedMayhemFlow, params: GlobalParams | None) -> Denominator:
    """The record's initial for a Mayhem curve whose ``MayhemState`` reconciled.

    ``flow.curve_reserve_without_agent`` is ``real_token_reserves − agent_net_sold``
    = ``initial_real − human_net``; a value above the record's initial would
    mean the humans hold a negative net, which no curve allows — so the record
    is not this curve's, and the honest answer is unknown. On the five live
    accounts of 12/09 it is at or below the initial, with equality on the
    fixture (``2sduGq…``: the humans' net was zero).
    """
    if params is None:
        return UNKNOWN
    initial = raw_subunits_to_tokens(params.initial_real_token_reserves)
    if flow.curve_reserve_without_agent > initial:
        return UNKNOWN
    return Denominator(initial, MAYHEM_STATE)


class GlobalParamsSource(Protocol):
    async def get_global_params(self, created_at_ms: int) -> GlobalParams: ...


def _effective_at(params: GlobalParams) -> datetime:
    """The record's ``timestamp`` is epoch **milliseconds** on the wire
    (``1752856476446`` for the 2025-07-18 record); a value that small it could
    only be seconds is read as seconds, so a synthetic record still resolves."""
    ts = params.timestamp
    return datetime.fromtimestamp(ts / 1000 if ts > 10**11 else ts, tz=UTC)


class GlobalParamsStore:
    """``/global-params/{created_ms}`` read once per refresh window and served to
    every coin created since the record took effect; a coin created *before*
    the cached record gets one read of its own, remembered. Each read costs
    one request of the curve budget (60/60 s), which is why the window is an
    hour and not a minute. A failed read is counted and returns whatever real
    record is cached — never a guess."""

    def __init__(self, source: GlobalParamsSource, *, refresh_s: float = 3600.0) -> None:
        self._source = source
        self._refresh = timedelta(seconds=refresh_s)
        self.latest: GlobalParams | None = None
        self.fetched_at: datetime | None = None
        self.reads = 0
        self.errors = 0
        self.last_error: str | None = None
        self._older: list[GlobalParams] = []

    async def _read(self, at: datetime) -> GlobalParams | None:
        self.reads += 1
        try:
            return await self._source.get_global_params(int(at.timestamp() * 1000))
        except Exception as exc:  # one failed read is a counted absence, not a crash
            self.errors += 1
            self.last_error = type(exc).__name__
            logger.warning("meme_global_params_read_failed", error=str(exc)[:200])
            return None

    async def resolve(self, created_at: datetime | None, *, now: datetime) -> GlobalParams | None:
        """The record in force at ``created_at`` (``None`` = the latest known)."""
        if self.fetched_at is None or now - self.fetched_at >= self._refresh:
            latest = await self._read(now)
            if latest is not None:
                self.latest, self.fetched_at = latest, now
        if self.latest is None or created_at is None:
            return self.latest
        if created_at >= _effective_at(self.latest):
            return self.latest
        for older in self._older:
            if created_at >= _effective_at(older):
                return older
        record = await self._read(created_at)
        if record is not None:
            self._older.append(record)
            self._older.sort(key=_effective_at, reverse=True)
        return record
