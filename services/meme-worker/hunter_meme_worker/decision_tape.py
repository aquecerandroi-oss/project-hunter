"""What the event lane saw at the instant it decided (T4.89) — a pure snapshot
of :class:`~hunter_meme_worker.event_state.MintEventState`, no I/O, no clock.

R73 (``.claude/state/notes-R73.md`` §2/§6, KB-0153): the desk decides on the
``meme_event_gate_v1`` lane, over a WS tape held in memory and never persisted
trade by trade, while the only recorded tape (``meme_trades``) is a polling
copy that arrives ~44 s late (p90 ≈ 129 s). Every study that rebuilt "what
the desk knew" from ``meme_trades`` measured the wrong tape; H-010 died of it.
:func:`capture_decision_tape` is taken **synchronously, at the decision, before
the first ``await``**, only when the lane has something to record:

- ``trades`` — the newest :data:`SLICE_MAX` fills of the 60 s deque that had
  reached us by ``as_of``, arrival order, each with its two clocks and its slot
  (T4.89b, ``None`` when the source didn't have one — never invented). 50
  covers the judged minute of a typical mint (``AIRAA`` had 31 buys in it) and
  bounds a hot one; ``slice.in_window`` says how many there were, so a cut is
  never silent, and every aggregate below is over the whole window, not the
  slice;
- ``derived`` — 10/30/60 s windows (buys, sells, SOL each way, net, unique
  buyers without the creator — the 60 s one is
  :func:`~hunter_meme_worker.features_tape.tape_for`'s own minute), the largest
  net SOL buyer and the largest net token buyer since the subscription with
  their share of the curve's real SOL and of the supply (H-010), the creator's
  net position, the curve photo the shares divide by, the coverage, and (T4.89b,
  H-015) :func:`~hunter_meme_worker.decision_tape_creation.creation_bundle_json`'s
  ``creation_bundle`` — the SOL bought in the creation slot by wallets other
  than the creator, past the 60 s window's own reach.

**"Since birth" is proved, not assumed.** The ledger reconciles when Σ net SOL
of every wallet it saw is within :data:`RECONCILE_TOLERANCE` of the curve's
real SOL (the pump curve starts at zero — R73's own coverage test); otherwise
its values are still reported, with ``reason = not_covered_from_birth``.

**Evidence, not a reason.** The ``reasons`` block is marked
``kind = evidence``/``used_by_gate = false``: no criterion read it.

**Non-anticipation.** Every value carries its instant (``as_of`` for the whole
block, both clocks per trade, ``observed_at``/``received_at`` for the curve,
``known_at`` for the ledger). A capture is only taken at the state's frontier:
when anything newer than ``as_of`` already reached the state (the 60 s deque
may have evicted a fill the window needed; the ledger cannot rewind), it
refuses by name (``state_ahead_of_decision``) instead of answering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from typing import TYPE_CHECKING, Any, Final

from hunter_meme_worker.decision_tape_creation import creation_bundle_json
from hunter_meme_worker.event_wallets import (
    COVERAGE_GAP,
    NOT_COVERED_FROM_BIRTH,
    TOKENS_UNKNOWN,
    WALLETS_OVERFLOW,
)

if TYPE_CHECKING:
    from hunter_meme_worker.event_state import MintEventState
    from hunter_meme_worker.event_state_values import CurvePoint
    from hunter_meme_worker.event_wallets import WalletFlow
    from hunter_meme_worker.features_tape import TapeTrade

__all__ = [
    "FEATURE",
    "RECONCILE_TOLERANCE",
    "SLICE_MAX",
    "STATE_AHEAD",
    "TAPE_VERSION",
    "DecisionTape",
    "capture_decision_tape",
]

FEATURE: Final = "decision_tape"
"""``reasons[].feature`` of the evidence block this lane appends."""
TAPE_VERSION: Final = 3
"""T4.89b (H-015) added ``trades[].slot`` and ``derived.creation_bundle``
(version 2), then ``creation_bundle.early_slots``/``slot_source``/
``create_signature`` (version 3, after Astra's review) — a reader of an
earlier version still finds every field it knew."""
SLICE_MAX: Final = 50
WINDOWS_S: Final = (10, 30, 60)
RECONCILE_TOLERANCE: Final = Decimal("0.01")
"""|Σ net SOL − real SOL| ≤ 1 % of real SOL (R73 accepted 2 %); the gap itself
is recorded (``reconcile_gap_sol``) so a study can re-threshold."""
WINDOW_NOT_COVERED: Final = "window_not_covered"
STATE_AHEAD: Final = "state_ahead_of_decision"
_FRACTION = Decimal("0.000001")


def _iso(at: datetime | None) -> str | None:
    return None if at is None else at.isoformat()


def _plain(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _sol(lamports: int) -> str:
    return _plain(Decimal(lamports).scaleb(-9))


def _share(part: Decimal, whole: Decimal | None) -> str | None:
    if whole is None or whole <= 0:
        return None
    return str((part / whole).quantize(_FRACTION, ROUND_HALF_EVEN))


@dataclass(frozen=True, slots=True)
class DecisionTape:
    """One decision instant of one mint: the tape slice and what it derived."""

    mint: str
    series: str
    as_of: datetime
    trades: tuple[TapeTrade, ...]
    trades_in_window: int
    derived: dict[str, Any]

    def reasons_block(self) -> dict[str, Any]:
        """The derived fields as one ``meme_proposals.reasons`` entry."""
        return {"feature": FEATURE, "kind": "evidence", "used_by_gate": False, **self.derived}

    def trades_json(self) -> list[dict[str, Any]]:
        """The slice as JSON rows — built by the writer, off the hot path."""
        return [
            {
                "block_time": t.block_time.isoformat(),
                "received_at": t.received_at.isoformat(),
                "slot": t.slot,
                "side": t.side,
                "sol": _sol(t.sol_lamports),
                "tokens": (
                    None
                    if t.token_subunits is None
                    else _plain(Decimal(t.token_subunits).scaleb(-6))
                ),
                "trader": t.trader,
            }
            for t in self.trades
        ]


@dataclass(slots=True)
class _Window:
    buys: int = 0
    sells: int = 0
    inflow: int = 0
    outflow: int = 0
    buyers: set[str] = field(default_factory=set[str])

    def as_json(self) -> dict[str, Any]:
        return {
            "buys": self.buys,
            "sells": self.sells,
            "buy_sol": _sol(self.inflow),
            "sell_sol": _sol(self.outflow),
            "net_sol": _sol(self.inflow - self.outflow),
            "unique_buyers": len(self.buyers),
        }


def _windows(
    known: list[TapeTrade], as_of: datetime, *, creator: str | None, covered_since: datetime
) -> dict[str, Any]:
    """One pass over the known fills, three windows ``(as_of − w, as_of]`` by
    block time — ``tape_for``'s own bounds and its unique-buyer rule."""
    rows = [_Window() for _ in WINDOWS_S]
    starts = [as_of - timedelta(seconds=w) for w in WINDOWS_S]
    for t in known:  # already inside the widest window
        bt = t.block_time
        for row, start in zip(rows, starts, strict=True):
            if bt <= start:
                continue
            if t.side == "buy":
                row.buys += 1
                row.inflow += t.sol_lamports
                if t.trader != creator:
                    row.buyers.add(t.trader)
            else:
                row.sells += 1
                row.outflow += t.sol_lamports
    return {
        f"{w}s": {"reason": WINDOW_NOT_COVERED} if covered_since > start else row.as_json()
        for w, row, start in zip(WINDOWS_S, rows, starts, strict=True)
    }


def _curve_point(
    state: MintEventState, as_of: datetime, *, source: str | None = None
) -> CurvePoint | None:
    """The newest photo that had reached us (of ``source``, when given)."""
    for point in reversed(state.points):
        if point.received_at <= as_of and (source is None or point.source == source):
            return point
    return None


def _wallet(
    pair: tuple[str, WalletFlow] | None,
    *,
    creator: str | None,
    real_sol: Decimal | None,
    supply: Decimal | None,
    tokens_known: bool,
) -> dict[str, Any] | None:
    if pair is None:
        return None
    wallet, flow = pair
    net_tokens = Decimal(flow.net_subunits).scaleb(-6)
    return {
        "wallet": wallet,
        "is_creator": wallet == creator,
        "net_sol": _sol(flow.net_lamports),
        "bought_sol": _sol(flow.bought_lamports),
        "sold_sol": _sol(flow.sold_lamports),
        "net_tokens": _plain(net_tokens) if tokens_known else None,
        "buys": flow.buys,
        "sells": flow.sells,
        "share_of_real_sol": _share(Decimal(flow.net_lamports).scaleb(-9), real_sol),
        "share_of_supply": _share(net_tokens, supply) if tokens_known else None,
    }


def _holders(state: MintEventState, as_of: datetime, real_sol: Decimal | None) -> dict[str, Any]:
    """The ledger reconciles against the newest *trade*'s post-trade reserves —
    the same stream it sums; an account photo can run ahead of (or behind) the
    logs subscription. The shares divide by the newest photo (``real_sol``)."""
    ledger = state.wallets
    total = Decimal(ledger.net_lamports_sum).scaleb(-9)
    last_trade = _curve_point(state, as_of, source="trade_event")
    anchor = None if last_trade is None else last_trade.real_sol
    gap: Decimal | None = None
    reconciles = False
    if anchor is not None:
        gap = anchor - total
        reconciles = abs(gap) <= RECONCILE_TOLERANCE * anchor
    reason = (
        COVERAGE_GAP if ledger.gapped
        else WALLETS_OVERFLOW if ledger.overflow
        else NOT_COVERED_FROM_BIRTH if not reconciles
        else TOKENS_UNKNOWN if ledger.tokens_missing
        else None
    )  # fmt: skip
    creator = state.creator
    tokens_known = not ledger.tokens_missing
    kwargs: dict[str, Any] = {
        "creator": creator,
        "real_sol": real_sol,
        "supply": state.total_supply,
        "tokens_known": tokens_known,
    }
    own = ledger.flows.get(creator) if creator is not None else None
    by_sol, by_tokens = ledger.leaders()
    return {
        "ledger": {
            "since": state.subscribed_at.isoformat(),
            "known_at": _iso(ledger.newest_received),
            "wallets": len(ledger.flows),
            "net_sol_total": _plain(total),
            "reconcile_real_sol": None if anchor is None else _plain(anchor),
            "reconcile_gap_sol": None if gap is None else _plain(gap),
            "creator_initial_buy_seeded": ledger.seed_signature is not None,
            "gapped": ledger.gapped,
            "overflow": ledger.overflow,
            "tokens_missing": ledger.tokens_missing,
            "reason": reason,
        },
        "largest_net_buyer": _wallet(by_sol, **kwargs),
        "largest_holder": _wallet(by_tokens, **kwargs) if tokens_known else None,
        "creator": None if creator is None or own is None else _wallet((creator, own), **kwargs),
    }


def _refused(state: MintEventState, as_of: datetime, series: str) -> DecisionTape:
    derived: dict[str, Any] = {
        "version": TAPE_VERSION,
        "series": series,
        "as_of": as_of.isoformat(),
        "reason": STATE_AHEAD,
        "state_newest_received_at": _iso(state.last_event_at),
    }
    return DecisionTape(state.mint, series, as_of, (), 0, derived)


def capture_decision_tape(state: MintEventState, *, as_of: datetime, series: str) -> DecisionTape:
    """The snapshot at ``as_of`` — only what had reached us by then."""
    if state.last_event_at is not None and state.last_event_at > as_of:
        return _refused(state, as_of, series)
    start = as_of - timedelta(seconds=WINDOWS_S[-1])
    # At the frontier every entry already has ``received_at <= as_of``.
    known = [t for t in state.trades if start < t.block_time <= as_of]
    point = _curve_point(state, as_of)
    real_sol = None if point is None else point.real_sol
    trades = tuple(known[-SLICE_MAX:])
    holders = _holders(state, as_of, real_sol)
    derived: dict[str, Any] = {
        "version": TAPE_VERSION,
        "series": series,
        "as_of": as_of.isoformat(),
        "reason": None,
        "coverage": {
            "subscribed_at": state.subscribed_at.isoformat(),
            "first_seen_at": _iso(state.first_seen_at),
            "covered_since": state.covered_since.isoformat(),
            "gaps": state.gaps,
        },
        "curve": {
            "real_sol": None if real_sol is None else _plain(real_sol),
            "observed_at": None if point is None else point.observed_at.isoformat(),
            "received_at": None if point is None else point.received_at.isoformat(),
            "total_supply": None if state.total_supply is None else _plain(state.total_supply),
        },
        "windows": _windows(known, as_of, creator=state.creator, covered_since=state.covered_since),
        **holders,
        "creation_bundle": creation_bundle_json(state, ledger_reason=holders["ledger"]["reason"]),
        "slice": {"trades": len(trades), "in_window": len(known), "max": SLICE_MAX},
    }
    return DecisionTape(state.mint, series, as_of, trades, len(known), derived)
