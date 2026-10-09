"""What the copy lane's hot path hands to its executor, and the named vocabulary of every refusal
and censor (H-037). Pure data: no IO, no clock.

The hot path (``copy_book.py``) decides **in memory** and emits one of the jobs below; the
executor (``copy_exec.py``) prices and persists them off the hot path. Every instant is a
timezone-aware UTC ``datetime``; :func:`ms_iso` writes it with millisecond precision, which is
the precision the lane claims (the chain's own ``block_time`` is whole seconds — that is the
chain's resolution, not ours).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Final, Literal

if TYPE_CHECKING:
    from hunter_exchanges.pumpfun.leader_events import LeaderEvent, LeaderGap

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
    "RecordGap",
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
AFTER_HORIZON: Final = "after_horizon"
RULE_SET_RETIRED: Final = "rule_set_retired"
FUNIL_INDISPONIVEL: Final = "funil_indisponivel"

SKIP_REASONS: Final = frozenset(
    {
        UNKNOWN_WALLET,
        DUPLICATE_SIGNATURE,
        UNCONFIRMED_IGNORED,
        ALREADY_OBSERVED,
        SELL_WITHOUT_ENTRY,
        EXIT_NOT_TRIGGERED,
        BEFORE_T0,
        AFTER_HORIZON,
        RULE_SET_RETIRED,
        FUNIL_INDISPONIVEL,
    }
)

# --- exits ---------------------------------------------------------------------------------------
EXIT_LEADER_FULL: Final = "leader_exit_full"
EXIT_LEADER_PEAK_DROP: Final = "leader_peak_drop"
EXIT_LEADER_TRANSFER: Final = "leader_transfer"
EXIT_SAFETY_STOP: Final = "safety_stop"
EXIT_TIME_CAP: Final = "time_cap"


def ms_iso(value: datetime) -> str:
    """ISO-8601 with millisecond precision — the lane's stamp format."""
    return value.isoformat(timespec="milliseconds")


@dataclass(frozen=True, slots=True)
class LeaderRef:
    """What we know of the leader's transaction behind a decision (stored on the row)."""

    wallet: str
    stratum: str
    signature: str
    slot: int
    block_time: datetime | None
    observed_at: datetime
    """The event's ``first_seen_at``: our clock when the first leg woke ``recv``."""
    fields_complete_at: datetime
    source: str
    confirmed: bool
    token_delta_atoms: int
    sol_delta_lamports: int | None
    position_after_atoms: int
    kind: str = "unknown"
    multi_mint: bool = False
    server_ts: datetime | None = None

    def as_json(self) -> dict[str, Any]:
        return {
            "wallet": self.wallet,
            "stratum": self.stratum,
            "signature": self.signature,
            "slot": self.slot,
            "block_time": None if self.block_time is None else ms_iso(self.block_time),
            "observed_at": ms_iso(self.observed_at),
            "first_seen_at": ms_iso(self.observed_at),
            "fields_complete_at": ms_iso(self.fields_complete_at),
            "server_ts": None if self.server_ts is None else ms_iso(self.server_ts),
            "kind": self.kind,
            "multi_mint": self.multi_mint,
            "source": self.source,
            "confirmed_at_decision": self.confirmed,
            "token_delta_atoms": self.token_delta_atoms,
            "sol_delta_lamports": self.sol_delta_lamports,
            "position_after_atoms": self.position_after_atoms,
        }


def leader_ref(event: LeaderEvent, stratum: str) -> LeaderRef:
    return LeaderRef(
        wallet=event.wallet,
        stratum=stratum,
        signature=event.signature,
        slot=event.slot,
        block_time=event.block_time,
        observed_at=event.first_seen_at,
        fields_complete_at=event.fields_complete_at,
        source=event.source,
        confirmed=event.confirmed,
        token_delta_atoms=event.token_delta_atoms,
        sol_delta_lamports=event.sol_delta_lamports,
        position_after_atoms=event.position_after_atoms,
        kind=event.kind,
        multi_mint=event.multi_mint,
        server_ts=event.server_ts,
    )


@dataclass(frozen=True, slots=True)
class OpenIntent:
    """Buy ``mint`` as ``leader`` did: priced at the market state at ``target_at``
    (= ``decided_at`` + the declared execution latency), never at the leader's price."""

    key: str
    mint: str
    leader: LeaderRef
    decided_at: datetime
    target_at: datetime


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


@dataclass(frozen=True, slots=True)
class CensorEntry:
    """An **admitted** attempt that ended unfilled by name before any price was read (no bet
    exists): an ``unfilled`` proposal, so the censoring is a row and not just a counter."""

    mint: str
    leader: LeaderRef
    reason: str
    decided_at: datetime


@dataclass(frozen=True, slots=True)
class RejectEntry:
    """A first observation of a (leader, mint) pair that was **not** admitted: a ``rejected``
    funnel row born decided, with the named reason (``nao_primeira``, ``abaixo_do_piso``, ...)."""

    mint: str
    leader: LeaderRef
    reason: str
    decided_at: datetime


@dataclass(frozen=True, slots=True)
class ConfirmIntent:
    """The event behind ``key`` was confirmed ``delay_ms`` after we first acted on it."""

    key: str
    signature: str
    kind: Literal["entry", "exit"]
    delay_ms: int


@dataclass(frozen=True, slots=True)
class InvalidateIntent:
    """The event behind ``key`` never confirmed inside the timeout: the copy is invalid."""

    key: str
    signature: str
    kind: Literal["entry", "exit"]
    reason: str
    decided_at: datetime


@dataclass(frozen=True, slots=True)
class RecordGap:
    """A closed coverage hole to persist in ``meme_ingest_gaps`` (``copy_leader:<wallet>`` or ``:*``)."""

    gap: LeaderGap


Job = (
    OpenIntent
    | CloseIntent
    | CensorEntry
    | RejectEntry
    | ConfirmIntent
    | InvalidateIntent
    | RecordGap
)


def target_of(decided_at: datetime, latency_ms: int) -> datetime:
    return decided_at + timedelta(milliseconds=latency_ms)
