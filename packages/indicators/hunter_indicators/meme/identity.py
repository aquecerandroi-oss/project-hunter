"""The identity gate (T4.26, EXP-M8): pump.fun's own social fields, read once
per mint (``docs/PUMPFUN.md`` §1.3, ``ddl/meme_social.py``) — a diagnostic
block for every proposal, and **one** optional refusal.

The $TRUMP case (17/01/2025) decided nothing on chart or flow: a public
figure's own account announced a coin, and it went from zero to billions in
hours. ``has_twitter``/``twitter_kind``/``twitter_post_age_s`` are how "who
announced it, and how verifiable" reaches the funnel at all — the plantão's
M-P17 measured that a link to a specific **post** ≤ 10 min before creation
associates with the slower, organic cells.

Cross-cutting like :mod:`hunter_indicators.meme.pedigree`: applied beside a
set's own gate, never inside :class:`~hunter_indicators.meme.rules.EntryGate`
— a set that does not ask ``require_twitter`` never refuses over it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

__all__ = ["NO_TWITTER", "IdentityFeatures", "evaluate_identity_gate"]

NO_TWITTER: Final = "no_twitter"


@dataclass(frozen=True, slots=True)
class IdentityFeatures:
    """The identity block at proposal time. ``None`` = not observed, never a
    negative answer — the same reading every other feature in this funnel gives
    a missing input."""

    has_twitter: bool
    twitter_kind: str | None
    twitter_post_age_s: int | None
    """``created_at - twitter_post_at`` in seconds, only when ``twitter_kind ==
    'post'`` and both instants are known; positive means the post came first."""
    twitter_reuse_count: int | None
    has_website: bool
    has_telegram: bool
    description_len: int | None


def evaluate_identity_gate(features: IdentityFeatures, *, require_twitter: bool) -> tuple[str, ...]:
    """Off by default: a set that does not ask for a twitter handle never
    refuses over one being absent. On, refuses :data:`NO_TWITTER` when the
    mint carries none — every other field here is diagnostic only."""
    if require_twitter and not features.has_twitter:
        return (NO_TWITTER,)
    return ()
