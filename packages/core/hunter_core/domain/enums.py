"""Every enum defined in docs/DATABASE.md (plus docs/RISK_ENGINE.md §5-6, which
DATABASE.md references without spelling out values), as ``StrEnum``.

Member values are exactly as the docs spell them. Two casing families exist in
the docs themselves and are preserved on purpose:

- Enums given as an explicit ``name = A, B, C`` assignment (org_role,
  plan_tier, kill_switch_state, opportunity_status) or as backtick lists
  (anomaly_type, market_regime) are UPPER_SNAKE_CASE.
- Enums shown inline as ``column type (a|b|c)`` are lower_snake_case.

``ALL_ENUMS`` maps each Postgres enum type name (as named in DATABASE.md) to
its Python class, for a later test that keeps this module in sync with the
actual database enums created in T04.

A few DB columns are typed as an enum in DATABASE.md but the doc never spells
out their members (``market_status``, ``exchange_status``,
``subscription_status``, ``feature_category``). Those were marked INFERRED by
T03 with the reasoning; T04 (database-architect) reviewed all four and kept
them unchanged — they are the values ``0001_initial_schema`` creates, so
changing one now costs a migration.
"""

from __future__ import annotations

import re
import uuid
from enum import StrEnum
from typing import Final


class OrganizationRole(StrEnum):
    """``org_role`` — DATABASE.md §2."""

    OWNER = "OWNER"
    ADMIN = "ADMIN"
    TRADER = "TRADER"
    ANALYST = "ANALYST"
    VIEWER = "VIEWER"


class Plan(StrEnum):
    """``plan_tier`` — DATABASE.md §2."""

    FREE = "FREE"
    PRO = "PRO"
    QUANT = "QUANT"
    ENTERPRISE = "ENTERPRISE"


class KillSwitchState(StrEnum):
    """``kill_switch_state`` — DATABASE.md §2, RISK_ENGINE.md §5. Ordered least to
    most restrictive: ACTIVE < WARNING < TRADING_DISABLED < EMERGENCY.
    """

    ACTIVE = "ACTIVE"
    WARNING = "WARNING"
    TRADING_DISABLED = "TRADING_DISABLED"
    EMERGENCY = "EMERGENCY"


class MemberStatus(StrEnum):
    """``member_status`` — DATABASE.md §2 (organization_members.status)."""

    INVITED = "invited"
    ACTIVE = "active"
    SUSPENDED = "suspended"


class WorkspaceObjective(StrEnum):
    """``workspace_objective`` — DATABASE.md §2 (workspaces.objective)."""

    EXPLORE = "explore"
    PAPER_TRADING = "paper_trading"
    RESEARCH = "research"
    AUTOMATED_TRADING = "automated_trading"


class SubscriptionStatus(StrEnum):
    """``subscription_status`` — DATABASE.md §2 (subscriptions.status).

    INFERRED by T03, confirmed unchanged by T04: the doc types the column but
    never lists members. Modeled on the Stripe subscription lifecycle since
    ``ENABLE_STRIPE`` and ``subscriptions.provider`` (null|stripe) are the only
    hints; billing is Phase 3, so the minimal lifecycle is kept.
    """

    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"


class ExchangeStatus(StrEnum):
    """``exchange_status`` — DATABASE.md §3 (exchanges.status).

    INFERRED by T03, confirmed unchanged by T04: no members listed in the doc.
    Minimal lifecycle — nothing in the docs distinguishes a third state.
    """

    ACTIVE = "active"
    INACTIVE = "inactive"


class MarketType(StrEnum):
    """``market_type`` — DATABASE.md §3 (markets.market_type)."""

    SPOT = "spot"
    PERPETUAL = "perpetual"


class MarketStatus(StrEnum):
    """``market_status`` — DATABASE.md §3 (markets.status).

    INFERRED by T03, confirmed unchanged by T04: no members listed in the doc;
    ``markets.delisted_at`` implies at least ACTIVE/DELISTED, and exchanges do
    halt symbols without delisting them (SUSPENDED).
    """

    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELISTED = "delisted"


class Timeframe(StrEnum):
    """``candle_timeframe`` — DATABASE.md §4 (candles.timeframe)."""

    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"


class OrderSide(StrEnum):
    """``order_side`` — DATABASE.md §4 (liquidations.side) and §7 (orders.side)."""

    BUY = "buy"
    SELL = "sell"


class FeatureCategory(StrEnum):
    """``feature_category`` — DATABASE.md §5 (feature_definitions.category).

    INFERRED by T03, confirmed unchanged by T04: no members listed in the doc;
    mapped 1:1 from the feature groups in PIPELINE.md §2 (Preço, Volume,
    Volatilidade, Microestrutura, Momentum, Derivativos, Cross).
    """

    PRICE = "price"
    VOLUME = "volume"
    VOLATILITY = "volatility"
    MICROSTRUCTURE = "microstructure"
    MOMENTUM = "momentum"
    DERIVATIVES = "derivatives"
    CROSS = "cross"


class AnomalyType(StrEnum):
    """``anomaly_type`` — DATABASE.md §5, §17 and PIPELINE.md §3.

    The ten MVP (v1) detectors of the joint M2 decision plus the two Phase 2/3
    types the pipeline doc already names. ``TRADE_VELOCITY_SPIKE`` and
    ``MOMENTUM_SHIFT`` were added by ``0003_analysis`` with
    ``ADD VALUE ... BEFORE 'SOCIAL_SPIKE'``, which is why they sit with the v1
    group here: this class's order is the database's label order.
    ``CROSS_EXCHANGE_DIVERGENCE`` stays registered but no detector arms it until
    a second exchange exists (M1b).
    """

    VOLUME_SPIKE = "VOLUME_SPIKE"
    PRICE_ACCELERATION = "PRICE_ACCELERATION"
    VOLATILITY_EXPANSION = "VOLATILITY_EXPANSION"
    ORDERBOOK_IMBALANCE = "ORDERBOOK_IMBALANCE"
    OPEN_INTEREST_SPIKE = "OPEN_INTEREST_SPIKE"
    FUNDING_ANOMALY = "FUNDING_ANOMALY"
    LIQUIDATION_CLUSTER = "LIQUIDATION_CLUSTER"
    CROSS_EXCHANGE_DIVERGENCE = "CROSS_EXCHANGE_DIVERGENCE"
    TRADE_VELOCITY_SPIKE = "TRADE_VELOCITY_SPIKE"
    MOMENTUM_SHIFT = "MOMENTUM_SHIFT"
    SOCIAL_SPIKE = "SOCIAL_SPIKE"
    WHALE_ACTIVITY = "WHALE_ACTIVITY"


class AnomalyStatus(StrEnum):
    """``anomaly_status`` — DATABASE.md §5 (anomalies.status)."""

    ACTIVE = "active"
    RESOLVED = "resolved"
    EXPIRED = "expired"


class AnomalyEvaluationState(StrEnum):
    """``anomaly_evaluation_state`` — ``anomalies.evaluation_state``, added by
    ``0003_analysis`` (joint M2 decision, "Anomalias").

    A second axis, deliberately separate from ``AnomalyStatus``: that one says
    where the anomaly is in its ``active -> resolved/expired`` lifecycle, this
    one says whether the data behind it can still be believed.

    - ``OK`` — evaluated against fresh, eligible data;
    - ``STALE`` — the source is late or degraded, so the anomaly may not feed a
      score;
    - ``UNKNOWN`` — no data arrived at all for this evaluation.

    The pair that matters is ``active + unknown``: an anomaly whose feed went
    away stays *active* and becomes ineligible. It is never resolved by absence
    — "we stopped looking" is not "it stopped happening".
    """

    OK = "ok"
    STALE = "stale"
    UNKNOWN = "unknown"


class RegimeScope(StrEnum):
    """``regime_scope`` — DATABASE.md §5 (market_regimes.scope)."""

    GLOBAL = "global"
    BTC = "btc"


class MarketRegime(StrEnum):
    """``market_regime`` — DATABASE.md §5, §17, PIPELINE.md §4. v0 (M2) plus
    the v1 (Phase 2) values the pipeline doc already names.

    ``UNKNOWN`` (``0003_analysis``) is the classifier's warm-up state, and it is a
    *classification*, not a missing value: while the 30 days of 1-minute candles
    the volatility percentile needs are not yet durable, the regime is honestly
    unknown and the reason goes in ``supporting_features``. A NULL would have let
    every consumer invent its own default; ``UNKNOWN`` makes them handle it.
    """

    BTC_BULL = "BTC_BULL"
    BTC_BEAR = "BTC_BEAR"
    SIDEWAYS = "SIDEWAYS"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    ALT_EXPANSION = "ALT_EXPANSION"
    PANIC = "PANIC"
    LIQUIDITY_CONTRACTION = "LIQUIDITY_CONTRACTION"
    UNKNOWN = "UNKNOWN"


class TradeDirection(StrEnum):
    """``trade_direction`` — DATABASE.md §5 (opportunities.direction) and §6
    (agent_signals.direction, agents.allowed_directions).
    """

    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


SignalDirection = TradeDirection
"""``agent_signals.direction`` reuses the ``trade_direction`` Postgres enum; this
alias is exported under the name used for signals, per the T03 brief. It is
intentionally NOT a second entry in ``ALL_ENUMS`` — there is only one DB type.
"""


class OpportunityStatus(StrEnum):
    """``opportunity_status`` — DATABASE.md §5 and §17.

    ``IN_POSITION`` and ``BLOCKED_BY_RISK`` are deliberately excluded: the doc
    states they are derived per organization at read time and are never stored in
    this column — the same opportunity can be in position for one tenant and
    blocked by risk for another, and a global column cannot say both.

    ``EXTENDED`` (``0003_analysis``) is the one global status the joint M2
    decision adds. Precedence, highest first: ``EXPIRED`` (terminal) >
    ``EXTENDED`` > ``ENTRY_CANDIDATE`` > ``HOT`` > ``ANOMALY`` > ``WATCHING`` >
    ``NORMAL``. Declaration order below is the *database's* label order
    (``0003`` adds ``EXTENDED`` with ``BEFORE 'EXPIRED'``), not the precedence.

    ``NORMAL`` never *opens* an episode, but it is a valid temporary state of one
    already open: the row keeps its id and starts ``below_40_since``.
    """

    NORMAL = "NORMAL"
    WATCHING = "WATCHING"
    ANOMALY = "ANOMALY"
    HOT = "HOT"
    ENTRY_CANDIDATE = "ENTRY_CANDIDATE"
    EXTENDED = "EXTENDED"
    EXPIRED = "EXPIRED"


class StrategyVersionStatus(StrEnum):
    """``strategy_version_status`` — DATABASE.md §6 (strategy_versions.status)."""

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class SignalStatus(StrEnum):
    """``signal_status`` — DATABASE.md §6 (agent_signals.status)."""

    ACTIVE = "active"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"


class OutcomeResult(StrEnum):
    """``outcome_result`` — DATABASE.md §6 (signal_outcomes.result)."""

    TARGET = "target"
    STOP = "stop"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"
    OPEN = "open"


class ShadowTrackingState(StrEnum):
    """``shadow_tracking_state`` — ``signal_outcomes.tracking_state``, added by
    ``0002_shadow_lab`` (docs/plans/SHADOW-LAB.md "Decisão conjunta" §4).

    The third axis of a shadow outcome, and the only one that answers "is this
    tracking still going?". ``SignalStatus`` says whether the *signal* is still
    valid, ``OutcomeResult`` says how the hypothetical trade *ended*, and this
    says where the tracking itself is:

    - ``PENDING_ENTRY`` - decided and persisted, waiting for the entry bar open;
    - ``ACTIVE`` - hypothetically in the market;
    - ``TERMINAL`` - resolved, with a financial result;
    - ``NO_ENTRY`` - never entered (late, geometry); never counted as open;
    - ``CENSORED`` - a bar the outcome needed is unrecoverable, so the result is
      unknown. Censorship never becomes ``expired``.

    ``TERMINAL``, ``NO_ENTRY`` and ``CENSORED`` never reopen.
    """

    PENDING_ENTRY = "pending_entry"
    ACTIVE = "active"
    TERMINAL = "terminal"
    NO_ENTRY = "no_entry"
    CENSORED = "censored"


_UUID_PATTERN = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
"""Lower-case hexadecimal, exactly as ``uuid.UUID.__str__`` renders it."""

REPLICATION_ARM_MIN: Final = 1
REPLICATION_ARM_MAX: Final = 99
"""The bounds of ``k`` in ``replication:<parent_version_id>:<k>``.

``1`` because a zeroth arm is not a sibling, and ``99`` because a replication
round is ten arms (``hunter_indicators.replication.SIBLINGS_N``) and two orders
of magnitude of headroom is already more tries than the protocol's
false-positive budget tolerates (REPLICATION.md §7). The pattern spells the
bound out (``[1-9][0-9]?``) rather than counting digits, so
``replication:<uuid>:01`` — a second spelling of arm 1 — is refused instead of
quietly becoming an eleventh population.
"""

SHADOW_COHORT_PATTERN = (
    f"^(prospective|replay:{_UUID_PATTERN}|replication:{_UUID_PATTERN}:[1-9][0-9]?)$"
)
"""The exact shape of ``shadow_episodes.cohort`` - also the CHECK in the database.

Not a Postgres ``ENUM``: a replay cohort carries its ``run_id`` and a
replication arm carries its parent version, so the set is open. It is still
closed in *shape*, and one regex shared by Python and the CHECK constraint is
what keeps a typo from quietly creating a fourth population that no report ever
mentions.

``prospective`` and ``replay:<uuid>`` are byte-identical to what
``0002_shadow_lab`` shipped; ``0012_replication`` only adds the third branch
(DATABASE.md §24).
"""

REPLAY_COHORT_PATTERN = f"^replay:{_UUID_PATTERN}$"
"""The replay branch of :data:`SHADOW_COHORT_PATTERN`, alone - ``replay_runs.cohort``.

A replay run's receipt (``0013_replay_runs``, DATABASE.md section 25) is never
``prospective`` and never a replication arm: those two are populations of the
live clock, and a row in ``replay_runs`` exists precisely because a window of
the past was replayed. So the table's CHECK is this pattern and not the wider
one - the intersection is spelled here once, instead of every reader having to
remember which of the three branches a receipt may carry.

Byte for byte the second branch of :data:`SHADOW_COHORT_PATTERN`;
``test_migrations.py`` proves both that and that ``0013``'s frozen copy still
agrees with this constant.
"""

_SHADOW_COHORT_RE = re.compile(SHADOW_COHORT_PATTERN)


class ShadowCohort:
    """``prospective``, ``replay:<run_id>`` or ``replication:<parent>:<k>``.

    SHADOW-LAB.md §1 and REPLICATION.md §4.4. The three are different
    populations by construction: the data used to develop a version is never
    that version's reserved forward evaluation, so a replay must never occupy
    the prospective tracking slot; and a replication sibling's signals have to
    be nameable as *the sibling's*, so the execution bridge can refuse them by
    cohort (``cohort_not_live``) and not only by ``purpose``.
    """

    PROSPECTIVE: Final = "prospective"
    REPLAY_PREFIX: Final = "replay:"
    REPLICATION_PREFIX: Final = "replication:"

    @staticmethod
    def replay(run_id: uuid.UUID) -> str:
        """The cohort label of one replay run."""
        return f"{ShadowCohort.REPLAY_PREFIX}{run_id}"

    @staticmethod
    def replication(parent_version_id: uuid.UUID, k: int) -> str:
        """The cohort label of one replication arm - ``k`` from 1 to 99.

        The label names the *arm*, not the sibling: a sibling is already its own
        ``strategy_version_id``. What the cohort buys is a name a consumer can
        refuse on sight, and a slot a sibling can never share with a replay of
        itself.
        """
        if not REPLICATION_ARM_MIN <= k <= REPLICATION_ARM_MAX:
            raise ValueError(
                f"replication arm {k} is outside "
                f"{REPLICATION_ARM_MIN}..{REPLICATION_ARM_MAX}: "
                "the cohort pattern (and the database CHECK) would refuse it"
            )
        return f"{ShadowCohort.REPLICATION_PREFIX}{parent_version_id}:{k}"

    @staticmethod
    def is_valid(cohort: str) -> bool:
        """``fullmatch``, not ``match``: Python's ``$`` also matches *before* a
        trailing newline, so a cohort ending in one passed here and was then
        refused by the database (POSIX ``$`` in ``~`` anchors at the true end of
        the string) and by :meth:`run_id`. Found by Astra's review of S0."""
        return _SHADOW_COHORT_RE.fullmatch(cohort) is not None

    @staticmethod
    def run_id(cohort: str) -> uuid.UUID | None:
        """The ``run_id`` of a replay cohort, or ``None`` for ``prospective``.

        Raises ``ValueError`` for anything the database would refuse, so a
        malformed cohort fails where it is read, not silently downstream.
        """
        if not ShadowCohort.is_valid(cohort):
            raise ValueError(f"{cohort!r} is not a valid shadow cohort")
        if cohort == ShadowCohort.PROSPECTIVE:
            return None
        return uuid.UUID(cohort.removeprefix(ShadowCohort.REPLAY_PREFIX))


class OpportunityStage(StrEnum):
    """``opportunity_stage`` — ``opportunities.stage``, added by ``0003_analysis``
    (joint M2 decision, "Estágio EARLY/DEVELOPING/EXTENDED").

    Where a move is in its life, from ``r = |return_1h| / atr_pct`` with the ATR
    of Wilder(14) over complete 15-minute UTC bars:

    - ``EARLY`` — ``r < 1.5`` **and** the symmetric confirmations fired;
    - ``DEVELOPING`` — ``1.5 <= r <= 4``;
    - ``EXTENDED`` — ``r > 4``, or the exhaustion alternative;
    - ``NONE`` — no stage could be computed (ATR warm-up, missing data).

    ``NONE`` is a member and not a NULL on purpose: "we cannot tell yet" is an
    answer the Radar has to show, and a nullable column would have let a consumer
    read the absence as EARLY.

    UPPER_SNAKE_CASE like ``OpportunityStatus``, its sibling column on the same
    table, rather than the lower-case draft in the superseded "Decisões deste
    plano" of ``docs/plans/M2.md`` — recorded in DATABASE.md §17.
    """

    EARLY = "EARLY"
    DEVELOPING = "DEVELOPING"
    EXTENDED = "EXTENDED"
    NONE = "NONE"


class BaselineSource(StrEnum):
    """``baseline_source`` — ``feature_baselines.source`` (``0003_analysis``).

    ``LIVE`` is computed from the feature snapshots the scanner wrote as they
    happened; ``BOOTSTRAP`` is computed by the same calculators over persisted
    candles, so a market does not have to wait a week for its first baseline. The
    column exists because the two are *not* interchangeable evidence: a bootstrap
    baseline may only be used for decisions after its ``available_at``, never
    back-dated to simulate knowledge nobody had.
    """

    LIVE = "live"
    BOOTSTRAP = "bootstrap"


class BaselineSampling(StrEnum):
    """``baseline_sampling`` — ``feature_baselines.sampling`` (``0003_analysis``).

    How the observations inside a bucket were drawn. One member today: the joint
    M2 decision fixes per-minute observations, 420 expected per (market, feature,
    UTC hour) bucket over seven days. A single-member enum is not a defect — it
    is the point: a second sampling policy has to arrive as a migration, and
    every baseline row already says which policy produced it, so two populations
    can never be silently averaged together.
    """

    PER_MINUTE = "per_minute"


class AgentStatus(StrEnum):
    """``agent_status`` — DATABASE.md §6 (agents.status)."""

    ENABLED = "enabled"
    PAUSED = "paused"
    DISABLED = "disabled"


class StatsWindow(StrEnum):
    """``stats_window`` — DATABASE.md §6 (agent_stats.window)."""

    ALL = "all"
    D7 = "7d"
    D30 = "30d"
    D90 = "90d"


class RiskPreset(StrEnum):
    """``risk_preset`` — DATABASE.md §7 (risk_profiles.preset).

    ``PAPER_V1`` is the M3 virtual wallet's profile (RISK_ENGINE.md §2): the
    Everton directive's numbers, seeded as a system preset. It sits *before*
    ``CUSTOM`` because ``CUSTOM`` is the open-ended wildcard and every named
    preset precedes it — the same ordering argument ``0003`` used to put
    ``EXTENDED`` before the terminal ``EXPIRED`` (DATABASE.md §17.1).
    """

    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"
    PAPER_V1 = "paper_v1"
    CUSTOM = "custom"


class PortfolioType(StrEnum):
    """``portfolio_type`` — DATABASE.md §7 (portfolios.type)."""

    PAPER = "paper"
    SHADOW = "shadow"
    LIVE = "live"


class PortfolioStatus(StrEnum):
    """``portfolio_status`` — DATABASE.md §7 (portfolios.status)."""

    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class ProposalStatus(StrEnum):
    """``proposal_status`` — DATABASE.md §7 (trade_proposals.status)."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    EXECUTED = "executed"
    FAILED = "failed"


class ProposalSource(StrEnum):
    """``proposal_source`` — DATABASE.md §18.3 (trade_proposals.source).

    *Where the admission request came in through*, which is not *who asked*:
    ``agent_id`` and the audit actor answer that. The M3 wallet has one live
    origin, ``MANUAL`` (RISK_ENGINE.md §8 — the operator's paper order, which
    goes through the same admission service as anything else); ``AGENT`` is
    frozen here as the interface T3.12/M4 will use so the bridge does not need
    a migration of its own. The shadow bridge is deliberately **not** a member:
    the joint decision leaves signal -> proposal to M4 (`docs/plans/M3.md`
    §"Decisão conjunta", item 9), and a label is a promise that something
    exists.
    """

    MANUAL = "manual"
    AGENT = "agent"


class ReservationState(StrEnum):
    """``reservation_state`` — DATABASE.md §18.3 (trade_proposals.reservation_state).

    The reservation's *tenure*, deliberately a different axis from
    ``proposal_status``, which is the decision's *label*. A proposal can be
    ``approved`` (a label that never changes: the Risk Engine did approve it)
    while its reservation has already been consumed by a fill, released by a
    cancellation or expired under the portfolio lock. Folding the two together
    is how a stale label ends up holding a slot nobody owns.

    ``CONSUMED`` is the fill *converting* the reserved slot into the position's
    slot — never a second slot for the same entry (M3 joint decision, item 4).
    """

    NONE = "none"
    HELD = "held"
    CONSUMED = "consumed"
    RELEASED = "released"
    EXPIRED = "expired"


class ExitIntentState(StrEnum):
    """``exit_intent_state`` — DATABASE.md §18.4 (portfolio_exit_intents.state).

    RISK_ENGINE.md §10: an exit *attempt* ends, but the *intention* survives for
    the remaining quantity. ``BLOCKED_RESIDUAL`` is the leftover below the
    exchange minimum — accounted and visible, never fictitiously settled — and
    is **not** terminal: it returns to ``OPEN`` when price or filters make the
    remainder tradable again. ``VOIDED`` is the honest terminal for an intention
    whose quantity was liquidated by a *competing* protection (a stop that took
    the whole position leaves the target with nothing to sell); it exists so
    that intention never has to be handed a fictitious fill to reach
    ``FULFILLED``.
    """

    OPEN = "open"
    BLOCKED_RESIDUAL = "blocked_residual"
    FULFILLED = "fulfilled"
    SUPERSEDED = "superseded"
    VOIDED = "voided"


class ParticipationEntryKind(StrEnum):
    """``participation_entry_kind`` — DATABASE.md §18.5.

    The three effects the participation budget of RISK_ENGINE.md §4 knows:
    ``RESERVED`` when an admission commits notional, ``EXECUTED`` when a fill
    turns part of that commitment into real consumption inside the 60 s window,
    and ``RELEASED`` when a terminal cancellation gives back **only the
    unexecuted** part.
    """

    RESERVED = "reserved"
    EXECUTED = "executed"
    RELEASED = "released"


class OrderType(StrEnum):
    """``order_type`` — DATABASE.md §7 (orders.type)."""

    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"
    TAKE_PROFIT = "take_profit"


class OrderPurpose(StrEnum):
    """``order_purpose`` — DATABASE.md §7 (orders.purpose)."""

    ENTRY = "entry"
    STOP = "stop"
    TARGET = "target"
    EXIT = "exit"
    REDUCE = "reduce"


class ExecutionMode(StrEnum):
    """``execution_mode`` — DATABASE.md §7 (orders.execution_mode)."""

    PAPER = "paper"
    SHADOW = "shadow"
    LIVE = "live"


class LiquidityRole(StrEnum):
    """``liquidity_role`` — DATABASE.md §7 (fills.liquidity).

    The doc spells the members inline (``liquidity (maker|taker)``) but never
    names the type; T04 named it ``liquidity_role`` so the closed set is a
    Postgres enum like every other closed set, per §1 ("Enums: tipos ENUM do
    Postgres, um por conceito").
    """

    MAKER = "maker"
    TAKER = "taker"


class OrderStatus(StrEnum):
    """``order_status`` — DATABASE.md §7 (orders.status)."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class PositionStatus(StrEnum):
    """``position_status`` — DATABASE.md §7 (positions.status)."""

    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"


class ExitReason(StrEnum):
    """``exit_reason`` — DATABASE.md §7 (trades.exit_reason)."""

    TARGET = "target"
    STOP = "stop"
    INVALIDATION = "invalidation"
    MANUAL = "manual"
    KILL_SWITCH = "kill_switch"
    EXPIRED = "expired"
    RISK_EVENT = "risk_event"


class RiskEventType(StrEnum):
    """``risk_event_type`` — DATABASE.md §7 (risk_events.type); members spelled
    out in RISK_ENGINE.md §8 (v2).

    ``0006_paper_wallet`` adds the three the v2 contract names and v1 did not
    have. Each is a distinction the engine has to be able to *publish*, not just
    compute: ``proposal_unavailable_input`` because "rejected for not fitting"
    and "not evaluated for want of data" are different facts (§7);
    ``participation_capped`` because the 1 % participation ceiling is the limit
    the directive expects to bind most often and D2 promises to measure; and
    ``beta_missing`` because "no validated beta, shadow only" is a directive
    rule whose firing has to be visible.
    """

    LIMITS_CHANGED = "limits_changed"
    PROPOSAL_REJECTED = "proposal_rejected"
    PROPOSAL_UNAVAILABLE_INPUT = "proposal_unavailable_input"
    DAILY_LOSS_WARNING = "daily_loss_warning"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    DRAWDOWN_WARNING = "drawdown_warning"
    DRAWDOWN_LIMIT = "drawdown_limit"
    EXPOSURE_LIMIT = "exposure_limit"
    PARTICIPATION_CAPPED = "participation_capped"
    BETA_MISSING = "beta_missing"
    DATA_DEGRADED_IN_POSITION = "data_degraded_in_position"
    KILL_SWITCH_CHANGED = "kill_switch_changed"
    STOP_SLIPPAGE_EXCESS = "stop_slippage_excess"
    POSITION_STALE_PRICE = "position_stale_price"


class RiskEventSeverity(StrEnum):
    """``event_severity`` — DATABASE.md §7 (risk_events.severity) and §12
    (system_events.level) share this Postgres enum. RISK_ENGINE.md §6 notes
    risk events in practice only ever use info/warning/critical, but the
    column type (also used by system_events) has all five levels.
    """

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class KillSwitchScope(StrEnum):
    """``ks_scope`` — DATABASE.md §7 (kill_switch_transitions.scope)."""

    SYSTEM = "system"
    ORGANIZATION = "organization"
    PORTFOLIO = "portfolio"


class ConnectionStatus(StrEnum):
    """``connection_status`` — DATABASE.md §8 (exchange_connections.status)."""

    PENDING = "pending"
    VALID = "valid"
    INVALID = "invalid"
    REVOKED = "revoked"


class BacktestStatus(StrEnum):
    """``backtest_status`` — DATABASE.md §9 (backtests.status)."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BacktestWarningCode(StrEnum):
    """``backtest_results.warnings[].code`` — DATABASE.md §9."""

    OVERFITTING = "overfitting"
    LEAKAGE = "leakage"
    LOOKAHEAD = "lookahead"


class IntelligenceSourceKind(StrEnum):
    """``intelligence_sources.key`` — DATABASE.md §10. The doc gives one unique
    identifier per source; it doubles as the source's kind.
    """

    NEWS = "news"
    REDDIT = "reddit"
    X = "x"
    GOOGLE_TRENDS = "google_trends"
    ONCHAIN = "onchain"
    WHALES = "whales"
    LISTINGS = "listings"
    UNLOCKS = "unlocks"
    ANNOUNCEMENTS = "announcements"


class AlertChannel(StrEnum):
    """``notifications.channel`` — DATABASE.md §11."""

    IN_APP = "in_app"
    EMAIL = "email"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    PUSH = "push"


class NotificationStatus(StrEnum):
    """``notifications.status`` — DATABASE.md §11."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    READ = "read"


class WorkerHeartbeatStatus(StrEnum):
    """``worker_heartbeats.status`` — DATABASE.md §12."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    STALE = "stale"
    DOWN = "down"


ALL_ENUMS: dict[str, type[StrEnum]] = {
    "org_role": OrganizationRole,
    "plan_tier": Plan,
    "kill_switch_state": KillSwitchState,
    "member_status": MemberStatus,
    "workspace_objective": WorkspaceObjective,
    "subscription_status": SubscriptionStatus,
    "exchange_status": ExchangeStatus,
    "market_type": MarketType,
    "market_status": MarketStatus,
    "candle_timeframe": Timeframe,
    "order_side": OrderSide,
    "feature_category": FeatureCategory,
    "anomaly_type": AnomalyType,
    "anomaly_status": AnomalyStatus,
    "anomaly_evaluation_state": AnomalyEvaluationState,
    "regime_scope": RegimeScope,
    "market_regime": MarketRegime,
    "trade_direction": TradeDirection,
    "opportunity_status": OpportunityStatus,
    "opportunity_stage": OpportunityStage,
    "baseline_source": BaselineSource,
    "baseline_sampling": BaselineSampling,
    "strategy_version_status": StrategyVersionStatus,
    "signal_status": SignalStatus,
    "outcome_result": OutcomeResult,
    "shadow_tracking_state": ShadowTrackingState,
    "agent_status": AgentStatus,
    "stats_window": StatsWindow,
    "risk_preset": RiskPreset,
    "portfolio_type": PortfolioType,
    "portfolio_status": PortfolioStatus,
    "proposal_status": ProposalStatus,
    "proposal_source": ProposalSource,
    "reservation_state": ReservationState,
    "exit_intent_state": ExitIntentState,
    "participation_entry_kind": ParticipationEntryKind,
    "order_type": OrderType,
    "order_purpose": OrderPurpose,
    "execution_mode": ExecutionMode,
    "liquidity_role": LiquidityRole,
    "order_status": OrderStatus,
    "position_status": PositionStatus,
    "exit_reason": ExitReason,
    "risk_event_type": RiskEventType,
    "event_severity": RiskEventSeverity,
    "ks_scope": KillSwitchScope,
    "connection_status": ConnectionStatus,
    "backtest_status": BacktestStatus,
    "backtest_warning_code": BacktestWarningCode,
    "intelligence_source_kind": IntelligenceSourceKind,
    "notification_channel": AlertChannel,
    "notification_status": NotificationStatus,
    "worker_heartbeat_status": WorkerHeartbeatStatus,
}
