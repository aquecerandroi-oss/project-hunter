"""The entry at the pullback (T4.91; H-016's mechanism, EXP-M24 tests
H-017) — the pure half: the two params, one armed entry and its running
max, and the filter the recheck at the trigger applies. No I/O and no clock: every
instant is an argument, every price a ``Decimal``. The bounded book is
:mod:`hunter_meme_worker.entry_pullback_book`; the event lane's glue is
:mod:`hunter_meme_worker.event_gate_pullback`.

**What it does.** A rule set carrying ``entry_pullback_pct`` (a decimal
string, ``"5"``) **and** ``entry_pullback_window_s`` (a JSON count, ``60``)
does not propose at the instant ``t0`` its gate passes on the event lane:
the mint is *armed*. From then on, every ``TradeEvent`` of that mint (never
an ``accountNotification`` — R77 §1.3: photos neither set the max nor fire)
is priced ``virtual_sol / virtual_token`` (post-trade marginal price) and
compared with the running max ``M``, which starts at the state known at
``t0`` (``EventGateRuntime.reserves``, trade or account — R77's "estado em
t0"). The first trade with ``price <= M x (1 - pct/100)`` fires (``M`` = the
max *before* that trade; a trade that raises ``M`` cannot fire). The window
is ``(t0, t0 + W]`` on ``received_at``: only trades folded **after** the
arming count (the start is exclusive by construction — a trade folded before
is part of ``M``; one received by ``t0`` but folded late, in a backlog, is
the state at ``t0`` too — it refreshes ``M`` and never fires), and the
deadline itself is inside. Without a fire, the
entry is the named non-entry :data:`NO_PULLBACK` only once the lane has
processed a frame received **after** the deadline (the queue is FIFO in
receipt order, and ``slotNotification`` keeps it moving every ~0.4 s — so a
trade received in time but still queued is never lost); a lane that cannot
prove that within :data:`STALL_S` ends the entry :data:`FEED_LOST`.

**Censored is not killed.** An operational loss (the feed, the cache, the
set changed under the wait — :data:`CENSORING`) is ``pullback_censored:<why>``
whether a trade touched the pullback afterwards or not, and leaves both sides
of the EXP-M24 pairing; a judgement (the creator sold, the gate refuses) is
``pullback_killed:<why>`` and counts as "did not enter" (0).

**Absent params, nothing changes**: :func:`entry_pullback_of` answers
``None`` and the lane never touches this module for that set.
``entry_pullback_pct`` is the switch — the window alone is inert (validated,
never acted on) so ``--set-param`` (one key per call) can write the window
first and the percent second, each document loading on its own.

**Bounded, in memory.** At most ``MAX_ARMED`` armed entries (the oldest
``t0`` is dropped with its own trail row :data:`DROPPED_CAP`); every (set,
mint) armed once is *spent* for ``SPENT_TTL_S`` (1 h, at most ``MAX_SPENT``
entries — ``entry_pullback_book``), far longer than a mint stays inside the
gate's age window, so a mint is armed once per set, as R77 counts one
decision per mint — within one process run. A process restart forgets
every armed and spent entry: nothing is proposed for them, no outcome row is
written (the ``armed`` row at ``t0`` stays without one — that is how a
restart shows in the trail) and the same mint may be armed again, so the
analysis keeps the **first** ``armed`` row per (set, mint).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from typing import TYPE_CHECKING, Any, Final

from hunter_core.domain.enums import FeatureCategory
from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.features.definitions import FeatureDefinition
from hunter_meme_worker.lab_params import decimal_of, optional_count
from hunter_meme_worker.lab_values import money_str

if TYPE_CHECKING:
    from hunter_meme_worker.lab_models import RuleSetSpec
    from hunter_meme_worker.proposals import ProposalDraft
    from hunter_meme_worker.proposals_row import GateRow

__all__ = [
    "ARMED",
    "CENSORED_PREFIX",
    "CENSORING",
    "DROPPED_CAP",
    "EVENT_LANE_ONLY",
    "FEED_LOST",
    "KILLED_PREFIX",
    "NO_PULLBACK",
    "PULLBACK_ARM_RULE_SET_ID",
    "PULLBACK_CONTROL_RULE_SET_ID",
    "STALL_S",
    "WAIVED_AT_TRIGGER",
    "ArmedEntry",
    "EntryPullback",
    "entry_pullback_of",
    "fatal_refusals",
    "outcome_of",
    "price_of",
]

PARAM_PCT: Final = "entry_pullback_pct"
PARAM_WINDOW_S: Final = "entry_pullback_window_s"
MAX_WINDOW_S: Final = 600
STALL_S: Final = 30
"""Seconds past the deadline after which an unproven expiry is :data:`FEED_LOST`."""

ARMED: Final = "entry_pullback_armed"
NO_PULLBACK: Final = "no_pullback"
CENSORED_PREFIX: Final = "pullback_censored:"
KILLED_PREFIX: Final = "pullback_killed:"
FEED_LOST: Final = f"{CENSORED_PREFIX}feed_lost"
"""Expired, but the mint left the book, its feed had a gap, or the queue gave
no proof: "no pullback" would be a claim the lane cannot make."""
CENSORING: Final = frozenset(
    {"feed_lost", "feed_gap", "no_base_row", "spec_changed", "creator_flow_overflow"}
)
"""Recheck reasons that say "the lane could not measure", not "the gate said no"."""
PULLBACK_ARM_RULE_SET_ID: Final = "01994d00-6c1a-7000-8000-00000000001d"
"""``recuo_v1/1`` (``0063``): its paper bets are subtracted from the desk's
pedigree read (``lab_repo_fast._PEDIGREE``), T4.85's precedent for the probe."""
PULLBACK_CONTROL_RULE_SET_ID: Final = "01994d00-6c1a-7000-8000-00000000001e"
"""``recuo_ctrl_v1/1`` (``0065``, T4.95, EXP-M25): ``recuo_v1/1`` minus the two
pullback keys — the immediate-entry pair of every arming. Subtracted from the
pedigree and from the tracker pins exactly like the arm."""
DROPPED_CAP: Final = "pullback_dropped_cap"
EVENT_LANE_ONLY: Final = "entry_pullback_event_lane_only"
"""The 15-second lane's own count for a pullback set's gate pass: it has no
live tape to wait on, so it never proposes for such a set."""

WAIVED_AT_TRIGGER: Final = frozenset(
    {
        # momentum, judged at t0, worsened by the pullback by construction
        "flow_not_positive",
        "buyers_below_min",
        "sells_ratio_above_max",
        "no_buys",
        "holders_not_rising",
        "holders_falling",
        "progress_not_rising",
        "distance_below_min",
        "distance_above_max",
        "no_higher_lows",
        "no_breakout",
        "new_wallets_below_min",
        "quick_flip_above_max",
        # the signal's validity: age was eligible at t0, the window is the wait
        "age_above_max",
    }
)
"""The only refusals the recheck at the trigger forgives, by exact name.
**Everything else kills** — fail closed: the creator, the pedigree, E2-b,
Mayhem, the curve, identity/event, ``already_open``, every ``*_unknown``,
``recent_drawdown`` (real SOL lost over its own window — not the price
pullback: a dump would pass as a "pullback"), the ticket against the volume
now (``participation_above_cap``, ``curve_volume_1m_zero``), the buys ceiling,
and any criterion added after T4.91 until someone argues it onto this list."""

ENTRY_PULLBACK_DEFINITION: Final = FeatureDefinition(
    key="entry_pullback",
    version=1,
    category=FeatureCategory.PRICE,
    inputs=(
        "solana_rpc_ws.trade_event.virtual_sol_reserves",
        "solana_rpc_ws.trade_event.virtual_token_reserves",
        "solana_rpc_ws.trade_event.received_at",
    ),
    description=(
        "After the gate passes at t0: the first trade in (t0, t0 + window_s] whose "
        "post-trade price vsol/vtok is <= M x (1 - pct/100), M = max(state at t0, "
        "trades since); none = no_pullback (H-016, R77 §1.3)."
    ),
    params={"price": "virtual_sol/virtual_token", "photos_fire": False},
)
"""Registered as every feature is; ``pct``/``window_s`` are the rule set's."""


@dataclass(frozen=True, slots=True)
class EntryPullback:
    pct: Decimal
    window_s: int

    def __post_init__(self) -> None:
        if not self.pct.is_finite() or not Decimal(0) < self.pct < Decimal(100):
            raise ValueError(f"{PARAM_PCT} must be in (0, 100), got {self.pct}")
        if not 0 < self.window_s <= MAX_WINDOW_S:
            raise ValueError(f"{PARAM_WINDOW_S} must be in 1..{MAX_WINDOW_S}, got {self.window_s}")


def entry_pullback_of(params: Mapping[str, Any], *, clock: str) -> EntryPullback | None:
    """``None`` unless ``entry_pullback_pct`` is set (the switch); then the
    window is required and the clock must be ``15s`` (the event lane's sets).
    Anything malformed never loads, so ``--set-param`` refuses it."""
    pct, window = params.get(PARAM_PCT), optional_count(PARAM_WINDOW_S, params.get(PARAM_WINDOW_S))
    if pct is None:
        return None
    if not isinstance(pct, str):
        raise TypeError(f'{PARAM_PCT} is a decimal string ("5"), never {pct!r}')
    if window is None:
        raise ValueError(f"{PARAM_PCT} needs {PARAM_WINDOW_S} (write the window first)")
    if clock != "15s":
        raise ValueError(f"an entry pullback needs the event lane's clock 15s, not {clock!r}")
    return EntryPullback(pct=decimal_of(pct), window_s=window)


def price_of(virtual_sol: Decimal, virtual_token: Decimal) -> Decimal | None:
    """SOL per token after the fill; ``None`` for a drained curve."""
    if virtual_sol <= 0 or virtual_token <= 0:
        return None
    with localcontext(CONTEXT):
        return virtual_sol / virtual_token


def outcome_of(reason: str) -> str:
    """The trail name of a recheck that did not propose."""
    return f"{CENSORED_PREFIX if reason in CENSORING else KILLED_PREFIX}{reason}"


def fatal_refusals(names: Iterable[str]) -> tuple[str, ...]:
    """The recheck's refusals that kill the entry, in the gate's order."""
    return tuple(name for name in names if name not in WAIVED_AT_TRIGGER)


@dataclass(slots=True)
class ArmedEntry:
    """One (set, mint) waiting for its pullback."""

    spec_id: str
    mint: str
    params: EntryPullback
    t0: datetime
    armed_max: Decimal
    gaps: int
    """``MintEventState.gaps`` at ``t0`` — any change means trades were missed."""
    creator_sells: int
    """The creator's sells seen by ``t0`` — one more kills the entry."""
    draft: ProposalDraft
    """The ``t0`` draft (its reasons carry the ``t0`` tape's block)."""
    row: GateRow
    spec: RuleSetSpec | None = None
    """The set as judged at ``t0`` — the recheck kills on any change."""
    t0_price: Decimal | None = None
    deepest_pct: Decimal = Decimal(0)
    trigger_price: Decimal | None = None
    trigger_at: datetime | None = None
    max_at_trigger: Decimal | None = None
    trigger_signature: str | None = None
    trigger_slot: int | None = None

    def __post_init__(self) -> None:
        self.t0_price = self.armed_max if self.t0_price is None else self.t0_price

    @property
    def deadline(self) -> datetime:
        return self.t0 + timedelta(seconds=self.params.window_s)

    @property
    def fired(self) -> bool:
        return self.trigger_price is not None

    def observe(
        self,
        price: Decimal,
        received_at: datetime,
        *,
        signature: str | None = None,
        slot: int | None = None,
    ) -> bool:
        """``True`` exactly once: at the trade that touches the pullback."""
        if self.fired or received_at > self.deadline:
            return False
        if received_at <= self.t0:  # received by t0, folded late: still the state at t0
            self.armed_max = self.t0_price = price
            return False
        with localcontext(CONTEXT):
            hundred = Decimal(100)
            threshold = self.armed_max * (hundred - self.params.pct) / hundred
            if price <= threshold:
                self.trigger_price, self.trigger_at = price, received_at
                self.max_at_trigger = self.armed_max
                self.trigger_signature, self.trigger_slot = signature, slot
                return True
            if price > self.armed_max:
                self.armed_max = price
            depth = (self.armed_max - price) * hundred / self.armed_max
            self.deepest_pct = max(self.deepest_pct, depth)
        return False

    def block(self, now: datetime) -> dict[str, Any]:
        """The ``reasons`` block of the proposal emitted at the trigger."""
        assert self.trigger_price is not None and self.max_at_trigger is not None
        return {
            "feature": ENTRY_PULLBACK_DEFINITION.key,
            "version": ENTRY_PULLBACK_DEFINITION.version,
            "t0": self.t0.isoformat(),
            "armed_max_price": money_str(self.max_at_trigger),
            "t0_price": None if self.t0_price is None else money_str(self.t0_price),
            "trigger_price": money_str(self.trigger_price),
            "trigger_at": None if self.trigger_at is None else self.trigger_at.isoformat(),
            "trigger_signature": self.trigger_signature,
            "trigger_slot": self.trigger_slot,
            "pct": money_str(self.params.pct),
            "window_s": self.params.window_s,
            "waited_s": money_str(Decimal(str((now - self.t0).total_seconds()))),
        }
