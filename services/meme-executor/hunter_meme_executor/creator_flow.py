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
- second-guess the tape: with ``creator_sold`` known, that value stands. A
  balance is an inference, a trade is a fact;
- treat an empty or absent token account as *unmeasured*. With a recorded
  allocation, an empty account means the tokens left, and the direction that
  refuses (``creator_net_seller``) is the safe one. That is the opposite of the
  creator-watch's rule (``creator_ata_missing`` = not measured) for the opposite
  reason: that loop has **no** base to compare against, and this one does.

Pure. The RPC call and its timeout belong to the caller (``entries.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_exchanges.pumpfun.curve import TOKEN_SUBUNITS_PER_TOKEN

if TYPE_CHECKING:
    from hunter_meme_executor.repo import TokenContext

__all__ = [
    "CHAIN_FLOW_SOURCE",
    "DEFAULT_SELL_TOLERANCE_PCT",
    "CreatorFlow",
    "creator_flow_from_chain",
    "needs_chain_creator_flow",
]

CHAIN_FLOW_SOURCE = "chain_ata_vs_initial"
"""The provenance written into the order's ``admission`` JSON. Named, because six
weeks from now "why did check 10 pass on this coin" has to be answerable from the
row alone (the gap T4.28h §5.2 left open for the dev share)."""

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
    """Is one RPC call worth it for this coin? Only when the tape is silent and
    the base is a real allocation."""
    if token.creator_sold is not None or token.creator is None:
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
