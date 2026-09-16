"""E2-b (T4.31, EXP-M9) — the **measured** signature of the forged fill, as a
criterion of the gate library beside :mod:`hunter_indicators.meme.pedigree`.

KB-0103 (14–16/09/2026, 390 labelled coins) and KB-0105 (replication
in 12 and 13/09, 307 labelled coins, 103 measured bets) found that what
separates a *forged* graduation from an organic one is **speed** and
**concentration**, not the three axes E2 v1 already reads:

- **born full** — the curve filled ``<= 60 s`` after the mint (88–94 % of the
  forged ones, 0,6–4,5 % of the organic ones);
- **concentration** — one wallet paid ``>= 35 %`` of all the SOL bought on the
  rise (median 0,77–0,97 among the forged, 0,056–0,066 among the organic).

Together they caught 92–100 % of the forged coins at a cost of 2,0–11,4 % of
the organic ones, while E2 v1 catches 35–54 % at a cost of 30–51 %.

**The guard, and why it exists.** The share of the largest buyer *at the
instant of the decision* is high by construction on a coin two minutes old
(median 0,428 with 21 buyers on the tape, KB-0105 §4): without a floor on the
number of buyers the criterion would refuse for **youth**, not for vice. So
the concentration leg only speaks with ``>= e2b_min_buyers`` distinct buyers
on the tape; under that floor it says nothing and the decomposition records
why.

**Unknown refuses by name.** A coin with no tape at the decision instant has
no share, and ``e2b_top_buyer_unknown`` is the refusal — the same reading
every other criterion of this library gives a missing feed (Astra's MUST-FIX
1). The arm exists partly to **measure how often that happens**: the tape
covered 21–25 % of the graduated coins in the days KB-0105 measured.

Registered as a gate is (``key``, ``version``, ``parameters``,
``description``, ``inputs``): moving a threshold is a **new version**, never
an edit of this one. Pure — no IO, no clock read; the caller brings the
instant (see ``hunter_meme_worker.lab_repo_e2b``).

**Research only.** This module is wired behind one rule set's own
``params.pedigree_e2b`` switch (``flow_v2/6``, migration ``0044``), never on
the desk's set: EXP-M9's default prediction is ``descartar``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

__all__ = [
    "E2B_INPUTS",
    "E2B_REFUSALS",
    "E2B_UNKNOWN_REFUSAL",
    "E2B_V1",
    "E2bFeatures",
    "E2bGate",
    "evaluate_e2b",
]

E2B_INPUTS: Final = (
    "meme_tokens.created_at",
    "meme_tokens.completed_at",
    "meme_trades.trader",
    "meme_trades.sol_lamports",
    "meme_trades.side",
    "meme_trades.block_time",
)
"""What the two legs are read from — our own database, at the instant judged."""

E2B_UNKNOWN_REFUSAL: Final = "e2b_top_buyer_unknown"
E2B_REFUSALS: Final = frozenset({"e2b_born_full", "e2b_top_buyer_share", E2B_UNKNOWN_REFUSAL})
"""The closed vocabulary this module can add to a gate's refusals."""


@dataclass(frozen=True, slots=True)
class E2bGate:
    """One registered E2-b gate. ``version`` bumps whenever a threshold moves."""

    key: str
    version: int
    description: str
    top_buyer_share_max: Decimal
    """A share **at or above** this refuses ``e2b_top_buyer_share``. The
    measurement reads ``>= 0,35`` (KB-0103 §3 rule G, KB-0105 §2), so the
    bound is inclusive on purpose."""
    min_buyers: int
    """The guard: under this many distinct buyers on the tape the
    concentration leg says nothing (KB-0105 §4, ressalva 2)."""
    born_full_s: int
    """``completed_at - created_at <= born_full_s`` refuses ``e2b_born_full``.
    ``completed_at`` is a **stamp of observation**, the earliest of four
    (KB-0103 §5): this leg reads "filled inside the same minute of the mint",
    never on-chain fill time."""
    inputs: tuple[str, ...] = E2B_INPUTS

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("version starts at 1")
        if not Decimal(0) < self.top_buyer_share_max <= Decimal(1):
            raise ValueError("a buyer's share is a fraction in (0, 1]")
        if self.min_buyers < 1:
            raise ValueError("the guard needs at least one buyer")
        if self.born_full_s < 1:
            raise ValueError("born full is at least one second")

    def as_parameters(self) -> Mapping[str, str]:
        return {
            "e2b_top_buyer_share_max": str(self.top_buyer_share_max),
            "e2b_min_buyers": str(self.min_buyers),
            "e2b_born_full_s": str(self.born_full_s),
        }


@dataclass(frozen=True, slots=True)
class E2bFeatures:
    """The two legs at the judged instant, each ``None`` when unmeasured."""

    top_buyer_share: Decimal | None
    """The largest buyer's share of the SOL bought since the mint, up to the
    judged instant. ``None`` = the tape said nothing (see ``tape_reason``)."""
    buyers: int | None
    """Distinct buyers on the same tape window; ``None`` with the share."""
    fill_seconds: int | None
    """``completed_at - created_at`` in seconds, **only** when the completion
    was already observed at or before the judged instant; ``None`` otherwise
    (a curve that fills later is not a coin born full — reading it would be
    look-ahead). Can be negative: 42,7 % of the graduated coins carry a
    ``completed_at`` at or before ``created_at`` (same block, KB-0103 §5)."""
    tape_reason: str | None = None
    """Why the share is unknown (``no_tape`` · ``no_sol_bought`` ·
    ``read_failed``); diagnostic, never a second refusal."""


E2B_V1: Final = E2bGate(
    key="pedigree_e2b",
    version=1,
    description=(
        "EXP-M9: refuse a curve that filled within 60 s of the mint and a coin whose "
        "largest buyer paid 35 % or more of the SOL bought since the mint (guard: at "
        "least 10 distinct buyers on the tape); an unmeasured share refuses by name."
    ),
    top_buyer_share_max=Decimal("0.35"),
    min_buyers=10,
    born_full_s=60,
)
"""The thresholds KB-0105 §3 recommends, frozen. The variant it names for a
parallel arm (``<= 30 s`` OR ``>= 45 %``) is a **new version**, not an edit."""


def _share_refusal(features: E2bFeatures, gate: E2bGate) -> str | None:
    """``e2b_top_buyer_unknown`` when nothing was measured; the guard first,
    then the threshold. A share under the floor of buyers is not "clean" — it
    is not asked, and the decomposition says so."""
    if features.top_buyer_share is None:
        return E2B_UNKNOWN_REFUSAL
    if features.buyers is None or features.buyers < gate.min_buyers:
        return None
    if features.top_buyer_share >= gate.top_buyer_share_max:
        return "e2b_top_buyer_share"
    return None


def evaluate_e2b(features: E2bFeatures, gate: E2bGate = E2B_V1) -> tuple[str, ...]:
    """The named refusals — empty when neither leg fires. Pure.

    ``e2b_born_full`` first (the cheaper, retrospective leg), then the
    concentration, so a coin that fires both is counted under both names and
    the arm can read each leg's own cost.
    """
    refusals: list[str] = []
    if features.fill_seconds is not None and features.fill_seconds <= gate.born_full_s:
        refusals.append("e2b_born_full")
    share = _share_refusal(features, gate)
    if share is not None:
        refusals.append(share)
    return tuple(refusals)
