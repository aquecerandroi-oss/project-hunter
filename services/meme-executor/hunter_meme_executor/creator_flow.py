"""T4.45 — check 10's input when the tape has not spoken yet: the creator's
balance on the chain against the allocation recorded at the create instant.

**The measurement this closes** (16/09/2026,
``obsidian/03-TRADING/Meme/Balanco-2026-09-16-mesa-real.md``): 27 of the day's 58
real orders were refused ``creator_flow_unknown``. ``meme_features_1m.creator_sold``
becomes non-NULL +123 to +441 s after the coin exists (R5), the desk proposes
between 30 and 300 s, so the executor was asking a question the tape could not
answer yet — and refusing, correctly, by name.

**Why this is now derivable and was not in T4.28g.** Its §2.3 refused to derive
the flow for one concrete reason: nothing held the creator's allocation *at
creation*. The only candidate base was the indexer's ``devHoldingsPercent``, a
**current** photograph whose first sample lands +114 to +419 s later — and with a
current photograph as the base, a creator who dumped everything at +20 s reads as
"balance ≥ base" and **passes** check 10. ``0048`` records the base at the create
instant (``meme_tokens.creator_initial_tokens``, from the ``create`` frame's own
``initialBuy``), so the comparison finally means what it says.

**What this module refuses to do**, each because of a specific failure:

- derive anything when the base is unknown (``NULL``) — "balance ≥ nothing" is
  vacuously true and would pass every pre-``0048`` coin;
- derive anything when the base is ``0`` — a creator who bought nothing at
  creation has no allocation to have sold, and answering "did not sell" about him
  is answering a different question;
- un-sell a sale the tape saw: with ``creator_sold = true`` that value stands
  and no RPC call is spent. A trade is a fact. **T4.56** narrowed this from "the
  tape wins whenever non-NULL": the fold's ``false`` means "no sale in the tape
  covered so far", and COVER (17/09/2026, R56 §3.2) proved it lags — the chain
  refused ``creator_net_seller`` at 19:46:56 BRT, the tape said ``false`` 23 s
  later, and the coin was bought. Now any source that saw the sale wins
  (:func:`resolve_creator_flow`), the tape's ``false`` fills in only when the
  chain read is absent or failed, and a chain sighting is remembered per mint
  (:class:`CreatorSoldMemory`) so a lagging tape never re-opens the coin;
- treat an empty or absent token account as *unmeasured*. With a recorded
  allocation, an empty account means the tokens left, and the direction that
  refuses (``creator_net_seller``) is the safe one. That is the opposite of the
  creator-watch's rule (``creator_ata_missing`` = not measured) for the opposite
  reason: that loop has **no** base to compare against, and this one does.

Pure. The RPC call and its timeout belong to the caller (``entries.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_exchanges.pumpfun.curve import TOKEN_SUBUNITS_PER_TOKEN

if TYPE_CHECKING:
    from hunter_meme_executor.repo import TokenContext

__all__ = [
    "CHAIN_FLOW_SOURCE",
    "CREATOR_SOLD_MEMORY_MAX_MINTS",
    "CREATOR_SOLD_MEMORY_TTL_S",
    "DEFAULT_SELL_TOLERANCE_PCT",
    "MEMORY_FLOW_SOURCE",
    "TAPE_FLOW_SOURCE",
    "CreatorFlow",
    "CreatorSoldMemory",
    "CreatorVerdict",
    "creator_flow_from_chain",
    "needs_chain_creator_flow",
    "resolve_creator_flow",
]

CHAIN_FLOW_SOURCE = "chain_ata_vs_initial"
"""The provenance written into the order's ``admission`` JSON. Named, because six
weeks from now "why did check 10 pass on this coin" has to be answerable from the
row alone (the gap T4.28h §5.2 left open for the dev share)."""

TAPE_FLOW_SOURCE = "meme_features_1m.creator_sold"
"""The 1-minute fold's *any sell by the creator in the tape covered so far*."""

MEMORY_FLOW_SOURCE = "executor_memory:creator_sold_on_chain"
"""T4.56 — this process remembered a chain read that said "sold" for the mint
(:class:`CreatorSoldMemory`); the instant is in ``remembered_sold_at``."""

CREATOR_SOLD_MEMORY_TTL_S = 30 * 60
"""T4.56 — how long a chain sighting of the creator's sale is held per mint. The
entry window closes at ``token_age_max_s`` (300 s in ``MEME_PAPER_V0``) and the
desk re-proposes for minutes, not hours; 30 min covers every re-proposal of a
coin this process refused, and a restart forgets it (the 120 s refusal cooldown
in Postgres is what survives one)."""

CREATOR_SOLD_MEMORY_MAX_MINTS = 4096
"""Upper bound on remembered mints, so a day of 25 000 creations cannot grow
the dict without limit; the oldest sighting leaves first."""

DEFAULT_SELL_TOLERANCE_PCT = Decimal("0.02")
"""``MEME_CREATOR_SELL_TOLERANCE_PCT`` — how much of his allocation a creator may
be missing before this reads as a sale. Not zero: the ``create`` frame's
``initialBuy`` is the quoted amount and the account can differ by dust, and a
false ``creator_net_seller`` costs a coin we would have bought. Not large: every
point of tolerance is a slice of a dump this check exists to catch."""


@dataclass(frozen=True, slots=True)
class CreatorFlow:
    """One derivation, with everything needed to re-check it by hand."""

    net_sol: Decimal
    """``-1`` (net seller) or ``+1`` (still holding) — the engine's own
    vocabulary (``MemeContext.creator_net_sol``), never a SOL amount: this read
    knows a balance, not a cash flow, and pretending otherwise would put an
    invented number in front of check 10."""
    source: str
    initial_tokens: Decimal
    balance_tokens: Decimal
    tolerance_pct: Decimal
    observed_at: datetime

    @property
    def sold(self) -> bool:
        return self.net_sol < 0

    def as_json(self) -> dict[str, str]:
        return {
            "source": self.source,
            "net_sol": str(self.net_sol),
            "initial_tokens": str(self.initial_tokens),
            "balance_tokens": str(self.balance_tokens),
            "tolerance_pct": str(self.tolerance_pct),
            "observed_at": self.observed_at.isoformat(),
        }


def needs_chain_creator_flow(token: TokenContext) -> bool:
    """Is one RPC call worth it for this coin? Only when the tape has not seen
    the sale (``NULL`` **or** ``false`` — T4.56) and the base is a real
    allocation. A tape ``true`` is settled: the read cannot change the answer."""
    if token.creator_sold is True or token.creator is None:
        return False
    initial = token.creator_initial_tokens
    return initial is not None and initial > 0


def creator_flow_from_chain(
    *,
    initial_tokens: Decimal,
    balance_subunits: int,
    tolerance_pct: Decimal,
    observed_at: datetime,
) -> CreatorFlow:
    """The creator's ATA balance (sub-units, as the chain counts) against the
    allocation the ``create`` frame recorded (tokens).

    The two units meet here, once: ``initialBuy`` is in tokens — the frame's own
    arithmetic proves it (``1 073 000 000 - initialBuy == vTokensInBondingCurve``)
    — and an SPL balance is in 6-decimal sub-units.
    """
    balance_tokens = Decimal(balance_subunits) / TOKEN_SUBUNITS_PER_TOKEN
    threshold = initial_tokens * (Decimal(1) - tolerance_pct)
    return CreatorFlow(
        net_sol=Decimal(-1) if balance_tokens < threshold else Decimal(1),
        source=CHAIN_FLOW_SOURCE,
        initial_tokens=initial_tokens,
        balance_tokens=balance_tokens,
        tolerance_pct=tolerance_pct,
        observed_at=observed_at,
    )


@dataclass(frozen=True, slots=True)
class CreatorVerdict:
    """T4.56 — what check 10 gets, and which source decided it. Every source
    that spoke is on record beside the decision, so "why did check 10 pass on
    this coin" is answerable from the order row alone."""

    net_sol: Decimal | None
    decided_by: str | None
    tape_sold: bool | None
    chain_net_sol: Decimal | None
    remembered_at: datetime | None

    def as_json(self) -> dict[str, str]:
        return {
            "net_sol": "" if self.net_sol is None else str(self.net_sol),
            "decided_by": self.decided_by or "",
            "tape_creator_sold": "" if self.tape_sold is None else str(self.tape_sold).lower(),
            "chain_net_sol": "" if self.chain_net_sol is None else str(self.chain_net_sol),
            "remembered_sold_at": ""
            if self.remembered_at is None
            else self.remembered_at.isoformat(),
        }


def resolve_creator_flow(
    *,
    tape_sold: bool | None,
    flow: CreatorFlow | None,
    remembered_at: datetime | None,
    chain_read_failed: bool = False,
) -> CreatorVerdict:
    """Pure. **Any source that saw the sale wins**; "did not sell" needs every
    present source to agree; with nothing present the answer stays unknown.

    Order among the sellers is only about the name written: the chain read of
    this very tick first (it is the freshest fact), then this process's memory
    of an earlier read, then the tape. Among the non-sellers the tape is named
    when it spoke (a trade record, agreeing with the balance), the chain when
    the tape was silent — T4.45's own case, unchanged.
    """
    chain = None if flow is None else flow.net_sol
    if flow is not None and flow.sold:
        decided: tuple[Decimal | None, str | None] = (Decimal(-1), flow.source)
    elif remembered_at is not None:
        decided = (Decimal(-1), MEMORY_FLOW_SOURCE)
    elif tape_sold:
        decided = (Decimal(-1), TAPE_FLOW_SOURCE)
    elif tape_sold is False and chain_read_failed:
        # Review T4.56: the tape said ``false`` but is the lagging source
        # (COVER: 23 s late); the chain was asked and did not answer. That is
        # unknown — refused ``creator_flow_unknown`` without cooldown, so the
        # next tick asks again — never a pass on the stale word alone.
        decided = (None, None)
    elif tape_sold is False:
        decided = (Decimal(1), TAPE_FLOW_SOURCE)
    elif flow is not None:
        decided = (flow.net_sol, flow.source)
    else:
        decided = (None, None)
    return CreatorVerdict(
        net_sol=decided[0],
        decided_by=decided[1],
        tape_sold=tape_sold,
        chain_net_sol=chain,
        remembered_at=remembered_at,
    )


class CreatorSoldMemory:
    """T4.56 — "the chain showed this creator sold, at <ts>", per mint, for
    :data:`CREATOR_SOLD_MEMORY_TTL_S`. Bounded two ways: by age on every access
    and by :data:`CREATOR_SOLD_MEMORY_MAX_MINTS` on every insert (oldest first —
    insertion order is sighting order, since a sighting is stamped with the
    tick's ``now``). The first sighting is the one kept: it is the instant the
    desk learned the fact, and a confirming read does not move it."""

    __slots__ = ("_max_mints", "_seen", "_ttl")

    def __init__(
        self,
        *,
        ttl_s: float = CREATOR_SOLD_MEMORY_TTL_S,
        max_mints: int = CREATOR_SOLD_MEMORY_MAX_MINTS,
    ) -> None:
        self._ttl = timedelta(seconds=ttl_s)
        self._max_mints = max(1, max_mints)
        self._seen: dict[str, datetime] = {}

    def __len__(self) -> int:
        return len(self._seen)

    def remember(self, mint: str, at: datetime) -> None:
        self._seen.setdefault(mint, at)
        while len(self._seen) > self._max_mints:
            del self._seen[next(iter(self._seen))]

    def seen_at(self, mint: str, *, now: datetime) -> datetime | None:
        self.prune(now)
        return self._seen.get(mint)

    def prune(self, now: datetime) -> None:
        expired = [mint for mint, at in self._seen.items() if now - at > self._ttl]
        for mint in expired:
            del self._seen[mint]
