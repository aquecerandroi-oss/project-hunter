"""What the copy lane's hot path hands to its executor, and the named vocabulary of every refusal
and censor (H-037). Pure data: no IO, no clock.

The hot path (``copy_book.py``) decides **in memory** and emits one of the jobs below; the
executor (``copy_exec.py``) prices and persists them off the hot path. Every instant is a
timezone-aware UTC ``datetime``; :func:`ms_iso` writes it with millisecond precision, which is
the precision the lane claims (the chain's own ``block_time`` is whole seconds — that is the
chain's resolution, not ours).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Final, Literal
from uuid import uuid4

from hunter_meme_worker.copy_ref import LeaderRef, leader_ref, ms_iso, window_ref

if TYPE_CHECKING:
    from hunter_exchanges.pumpfun.leader_events import LeaderGap

__all__ = [
    "CENSOR_REASONS",
    "REJECT_REASONS",
    "SKIP_REASONS",
    "UNFILLED_REASONS",
    "CensorEntry",
    "CloseIntent",
    "ConfirmIntent",
    "InvalidateIntent",
    "Job",
    "LeaderRef",
    "OpenIntent",
    "RecomposeDone",
    "RecordGap",
    "UnverifiedIntent",
    "window_ref",
    "RejectEntry",
    "leader_ref",
    "ms_iso",
]

# --- the funnel: a leader buy we saw and did not copy, one durable ``rejected`` row per first --------
# observation of a (leader, mint) pair (H-037 design §4.1). The strings are the design's and are
# what the frozen reading script groups by.
NAO_PRIMEIRA: Final = "nao_primeira"
ABAIXO_DO_PISO: Final = "abaixo_do_piso"
CO_COMPRA: Final = "co_compra"
TETO_DIA: Final = "teto_dia"
LACUNA: Final = "lacuna"
MULTI_MINT: Final = "multi_mint"
EVIDENCIA_INSUFICIENTE: Final = "evidencia_insuficiente"
VENUE_FORA_DO_ESCOPO: Final = "venue_fora_do_escopo"
RECOMPOSICAO_PENDENTE: Final = "recomposicao_pendente"
VISTO_NA_LACUNA: Final = "visto_na_lacuna"

REJECT_REASONS: Final = frozenset(
    {
        NAO_PRIMEIRA,
        ABAIXO_DO_PISO,
        CO_COMPRA,
        TETO_DIA,
        LACUNA,
        MULTI_MINT,
        EVIDENCIA_INSUFICIENTE,
        VENUE_FORA_DO_ESCOPO,
        RECOMPOSICAO_PENDENTE,
        VISTO_NA_LACUNA,
    }
)

# --- admitted but never filled: ``meme_proposals.status = 'unfilled'``, the key is consumed ----------
TETO_ABERTO: Final = "teto_aberto"
SOBRECARGA: Final = "sobrecarga"
SEM_ESTADO: Final = "sem_estado"
INSUFFICIENT_CURVE_RESERVES: Final = "insufficient_curve_reserves"

UNFILLED_REASONS: Final = frozenset(
    {TETO_ABERTO, SOBRECARGA, SEM_ESTADO, INSUFFICIENT_CURVE_RESERVES}
)

# --- a copy that became a bet and is closed ``indeterminate`` (priced by no one) ----------------------
LEADER_GAP_EXIT: Final = "leader_gap_exit"
MIGROU_FORA_DE_PRACA: Final = "migrou_fora_de_praca"
WORKER_RESTART_GAP: Final = "worker_restart_gap"
NO_EXIT_STATE: Final = "sem_estado_saida"
NO_POOL_TRADE: Final = "no_pool_trade_in_window"

CENSOR_REASONS: Final = (
    REJECT_REASONS
    | UNFILLED_REASONS
    | frozenset(
        {LEADER_GAP_EXIT, MIGROU_FORA_DE_PRACA, WORKER_RESTART_GAP, NO_EXIT_STATE, NO_POOL_TRADE}
    )
)
"""The closed vocabulary of every refusal and censor: ``meme_proposals.decision.reason`` for a rejected
funnel row, ``.refusal`` for an unfilled one, ``meme_paper_bets.outcome_quality_reason`` for a closed
copy that priced nothing. A new reason is a code change and a test, never a string at a call site."""

# --- invalidation: the event behind a copy was not confirmed; the copy STAYS in the primary -------------
INVALID_NOT_FOUND: Final = "not_found"
UNVERIFIED: Final = "unverified"
INVALID_DIVERGENT: Final = "divergent"
EXIT_INVALIDATED: Final = "invalidated"

# --- skipped: not a first observation, a duplicate or a stranger — counted, no row ---------------------
UNKNOWN_WALLET: Final = "unknown_wallet"
DUPLICATE_SIGNATURE: Final = "duplicate_signature"
UNCONFIRMED_IGNORED: Final = "unconfirmed_ignored"
ALREADY_OBSERVED: Final = "already_observed"
SELL_WITHOUT_ENTRY: Final = "sell_without_entry"
EXIT_NOT_TRIGGERED: Final = "exit_not_triggered"
BEFORE_T0: Final = "before_t0"
NOT_ARMED: Final = "not_armed"
AFTER_HORIZON: Final = "after_horizon"
RULE_SET_RETIRED: Final = "rule_set_retired"
FUNIL_INDISPONIVEL: Final = "funil_indisponivel"
WORKER_DOWNTIME: Final = "worker_downtime"

SKIP_REASONS: Final = frozenset(
    {
        UNKNOWN_WALLET,
        DUPLICATE_SIGNATURE,
        UNCONFIRMED_IGNORED,
        ALREADY_OBSERVED,
        SELL_WITHOUT_ENTRY,
        EXIT_NOT_TRIGGERED,
        BEFORE_T0,
        NOT_ARMED,
        AFTER_HORIZON,
        RULE_SET_RETIRED,
    }
)

# --- exits ---------------------------------------------------------------------------------------
EXIT_LEADER_FULL: Final = "leader_exit_full"
EXIT_LEADER_PEAK_DROP: Final = "leader_peak_drop"
EXIT_LEADER_TRANSFER: Final = "leader_transfer"
EXIT_SAFETY_STOP: Final = "safety_stop"
EXIT_TIME_CAP: Final = "time_cap"


def _oid() -> str:
    return uuid4().hex


@dataclass(frozen=True, slots=True)
class OpenIntent:
    """Buy ``mint`` as ``leader`` did: priced at the market state at ``target_at``
    (= ``decided_at`` + the declared execution latency), never at the leader's price."""

    key: str
    mint: str
    leader: LeaderRef
    decided_at: datetime
    target_at: datetime
    oid: str = field(default_factory=_oid)


@dataclass(frozen=True, slots=True)
class CloseIntent:
    """Sell the copy ``key``. ``leader`` is the leader's selling transaction, ``None`` for our own
    exits (safety stop, time cap). ``censor`` set = the exit cannot be priced and the copy is
    closed ``indeterminate`` with that reason instead."""

    key: str
    mint: str
    reason: str
    leader: LeaderRef | None
    decided_at: datetime
    target_at: datetime
    censor: str | None = None
    contaminated: str | None = None
    """Set when the copy lived across a gap or a restart: the sale is still priced (an own exit does
    not depend on the leader) but the copy leaves the primary set — it is flagged, never silently
    ``measured`` (the design's ``contaminated``)."""
    oid: str = field(default_factory=_oid)


@dataclass(frozen=True, slots=True)
class CensorEntry:
    """An **admitted** attempt that ended unfilled by name before any price was read (no bet
    exists): an ``unfilled`` proposal, so the censoring is a row and not just a counter."""

    mint: str
    leader: LeaderRef
    reason: str
    decided_at: datetime
    oid: str = field(default_factory=_oid)


@dataclass(frozen=True, slots=True)
class RejectEntry:
    """A first observation of a (leader, mint) pair that was **not** admitted: a ``rejected``
    funnel row born decided, with the named reason (``nao_primeira``, ``abaixo_do_piso``, ...)."""

    mint: str
    leader: LeaderRef
    reason: str
    decided_at: datetime
    oid: str = field(default_factory=_oid)


@dataclass(frozen=True, slots=True)
class RecomposeDone:
    """A leader's window was read from the chain's history: persist the pairs it bought inside the hole
    (``rejected/visto_na_lacuna``) and **then** the durable marker that the window is done - one job, so a
    crash can never leave the marker without the pairs."""

    wallet: str
    gap_id: str
    start: datetime
    end: datetime
    reason: str
    seen: tuple[RejectEntry, ...] = ()
    oid: str = field(default_factory=_oid)


@dataclass(frozen=True, slots=True)
class ConfirmIntent:
    """The event behind ``key`` was confirmed ``delay_ms`` after we first acted on it."""

    key: str
    signature: str
    kind: Literal["entry", "exit"]
    delay_ms: int
    post_reserves: dict[str, Any] | None = None
    """The market right after the leader's trade, as the chain reported it: the ``ideal`` sensitivity."""
    oid: str = field(default_factory=_oid)


@dataclass(frozen=True, slots=True)
class InvalidateIntent:
    """The event behind ``key`` never confirmed inside the timeout: the copy is invalid."""

    key: str
    signature: str
    kind: Literal["entry", "exit"]
    reason: str
    decided_at: datetime
    oid: str = field(default_factory=_oid)


@dataclass(frozen=True, slots=True)
class UnverifiedIntent:
    """Only ``rpc_error`` ever answered for the event behind ``key``: the copy is flagged
    ``unverified`` and kept — a node that did not answer is not a verdict."""

    key: str
    signature: str
    kind: Literal["entry", "exit"]
    decided_at: datetime
    oid: str = field(default_factory=_oid)


@dataclass(frozen=True, slots=True)
class RecordGap:
    """A coverage hole to persist in ``meme_ingest_gaps`` (``copy_leader:<wallet>`` or ``:*``): once when
    it **opens** and once when it closes (the table is append-only)."""

    gap: LeaderGap
    oid: str = field(default_factory=_oid)


Job = (
    OpenIntent
    | CloseIntent
    | CensorEntry
    | RejectEntry
    | ConfirmIntent
    | InvalidateIntent
    | UnverifiedIntent
    | RecordGap
    | RecomposeDone
)


def target_of(decided_at: datetime, latency_ms: int) -> datetime:
    return decided_at + timedelta(milliseconds=latency_ms)
