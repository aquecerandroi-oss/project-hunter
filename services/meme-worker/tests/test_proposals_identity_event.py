# pyright: reportPrivateUsage=false
"""T4.26 (EXP-M8) — the identity and event cross-cutting checks: off by
default (a set that does not ask never refuses and its reasons stay frozen,
``test_proposals_flow.py``'s own invariant), ``require_twitter`` refuses
``no_twitter`` and shows the identity block only for a set that asks,
``require_event`` refuses ``no_event`` unless the matched event is a
``confirmed`` public-figure/exchange/brand launch.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hunter_meme_worker.lab_models import RuleSetSpec
from hunter_meme_worker.proposals import evaluate_gate

from .test_paper_engine import PARAMS
from .test_proposals_flow import CLEAN, MINT, NOW, _fast_row, _flow_spec

pytestmark = pytest.mark.unit

POST_AT = datetime(2026, 9, 12, 3, 45, 19, tzinfo=UTC)


def _spec_with(**overrides: object) -> RuleSetSpec:
    return _flow_spec(**overrides)


def test_require_twitter_off_by_default() -> None:
    assert _flow_spec().require_twitter is False
    assert _flow_spec().require_event is False


def test_require_twitter_refuses_a_mint_with_no_twitter_link() -> None:
    spec = _spec_with(require_twitter=True)
    outcome = evaluate_gate(
        spec, [_fast_row()], now=NOW, ttl_s=120, already_open=frozenset(), pedigree={MINT: CLEAN}
    )
    assert outcome.drafts == []
    assert outcome.refusals == {"no_twitter": 1}


def test_require_twitter_passes_and_shows_the_identity_block() -> None:
    spec = _spec_with(require_twitter=True)
    row = _fast_row(
        twitter="x.com/CoachPatNFT/status/2098618936124375364",
        twitter_kind="post",
        twitter_post_at=POST_AT,
        twitter_reuse_count=3,
        website=None,
        telegram="t.me/coachpat",
        description="lets go",
    )
    outcome = evaluate_gate(
        spec, [row], now=NOW, ttl_s=120, already_open=frozenset(), pedigree={MINT: CLEAN}
    )
    assert outcome.refusals == {}
    (draft,) = outcome.drafts
    blocks = {r.get("feature"): r for r in draft.reasons[1:]}
    assert blocks["identity"] == {
        "feature": "identity",
        "has_twitter": True,
        "twitter_kind": "post",
        "twitter_post_age_s": int((row.created_at - POST_AT).total_seconds()),  # type: ignore[arg-type]
        "twitter_reuse_count": 3,
        "has_website": False,
        "has_telegram": True,
        "description_len": len("lets go"),
    }


def test_require_event_refuses_without_a_matching_confirmed_event() -> None:
    spec = _spec_with(require_event=True)
    outcome = evaluate_gate(
        spec, [_fast_row()], now=NOW, ttl_s=120, already_open=frozenset(), pedigree={MINT: CLEAN}
    )
    assert outcome.drafts == []
    assert outcome.refusals == {"no_event": 1}


@pytest.mark.parametrize(
    ("kind", "confidence", "allowed"),
    [
        ("public_figure_launch", "confirmed", True),
        ("exchange_listing", "confirmed", True),
        ("brand_launch", "confirmed", True),
        ("public_figure_launch", "reported", False),
        ("public_figure_launch", "rumor", False),
        ("viral_post", "confirmed", False),
    ],
)
def test_require_event_gates_on_kind_and_confidence(
    kind: str, confidence: str, allowed: bool
) -> None:
    spec = _spec_with(require_event=True)
    row = _fast_row(
        event_kind=kind,
        event_confidence=confidence,
        event_title="a launch",
        event_source="manual",
        event_observed_at=NOW,
    )
    outcome = evaluate_gate(
        spec, [row], now=NOW, ttl_s=120, already_open=frozenset(), pedigree={MINT: CLEAN}
    )
    if allowed:
        assert outcome.refusals == {}
        (draft,) = outcome.drafts
        blocks = {r.get("feature"): r for r in draft.reasons[1:]}
        assert blocks["event"]["kind"] == kind
        assert blocks["event"]["confidence"] == confidence
        assert blocks["event"]["title"] == "a launch"
        assert blocks["event"]["observed_at"] == NOW.isoformat()
    else:
        assert outcome.drafts == []
        assert outcome.refusals == {"no_event": 1}


def test_require_event_refuses_event_avoid_even_when_confirmed_and_allowed() -> None:
    """T4.26b: an ``avoid``-kind match outranks kind/confidence entirely — the
    same row that would otherwise pass ``test_require_event_gates_on_kind_and_
    confidence`` above is refused once the match itself is a warning."""
    spec = _spec_with(require_event=True)
    row = _fast_row(
        event_kind="public_figure_launch",
        event_confidence="confirmed",
        event_match_kind="avoid",
    )
    outcome = evaluate_gate(
        spec, [row], now=NOW, ttl_s=120, already_open=frozenset(), pedigree={MINT: CLEAN}
    )
    assert outcome.drafts == []
    assert outcome.refusals == {"event_avoid": 1}


def test_params_default_params_still_have_no_identity_or_event_switch() -> None:
    """``PARAMS`` (EXP-M1's own) reads exactly as before this task started."""
    assert "require_twitter" not in PARAMS and "require_event" not in PARAMS
