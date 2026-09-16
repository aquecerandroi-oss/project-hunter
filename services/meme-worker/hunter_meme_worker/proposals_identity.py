"""``GateRow`` → :class:`~hunter_indicators.meme.identity.IdentityFeatures` /
:class:`~hunter_indicators.meme.event_gate.EventFeatures` — split out of
``proposals.py`` for the 350-line budget (T4.26). Both blocks ride the same
join every other identity field already comes through (``lab_repo.py`` /
``lab_repo_fast.py``); no new query.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hunter_indicators.meme.event_gate import EventFeatures
from hunter_indicators.meme.identity import IdentityFeatures

if TYPE_CHECKING:
    from hunter_meme_worker.proposals_row import GateRow

__all__ = ["event_features_of", "identity_features_of"]


def identity_features_of(row: GateRow) -> IdentityFeatures:
    post_age_s: int | None = None
    if (
        row.twitter_kind == "post"
        and row.twitter_post_at is not None
        and row.created_at is not None
    ):
        post_age_s = int((row.created_at - row.twitter_post_at).total_seconds())
    return IdentityFeatures(
        has_twitter=row.twitter is not None,
        twitter_kind=row.twitter_kind,
        twitter_post_age_s=post_age_s,
        twitter_reuse_count=row.twitter_reuse_count,
        has_website=row.website is not None,
        has_telegram=row.telegram is not None,
        description_len=None if row.description is None else len(row.description),
    )


def event_features_of(row: GateRow) -> EventFeatures:
    return EventFeatures(
        kind=row.event_kind,
        confidence=row.event_confidence,
        title=row.event_title,
        source=row.event_source,
        observed_at=row.event_observed_at,
        match_kind=row.event_match_kind,
    )
