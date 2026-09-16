"""``hunter_indicators.meme.event_gate`` — T4.26/EXP-M8's cross-cutting event
requirement: off by default, and on, refuses everything but a ``confirmed``
public-figure/exchange/brand launch."""

from __future__ import annotations

import pytest

from hunter_indicators.meme.event_gate import (
    ALLOWED_EVENT_KINDS,
    NO_EVENT,
    EventFeatures,
    evaluate_event_gate,
)

pytestmark = pytest.mark.unit


def test_off_by_default_never_refuses() -> None:
    assert evaluate_event_gate(EventFeatures(kind=None, confidence=None), require_event=False) == ()


def test_on_refuses_a_mint_with_no_matched_event() -> None:
    features = EventFeatures(kind=None, confidence=None)
    assert evaluate_event_gate(features, require_event=True) == (NO_EVENT,)


@pytest.mark.parametrize("kind", ALLOWED_EVENT_KINDS)
def test_on_passes_a_confirmed_allowed_kind(kind: str) -> None:
    features = EventFeatures(kind=kind, confidence="confirmed")
    assert evaluate_event_gate(features, require_event=True) == ()


@pytest.mark.parametrize("confidence", ["reported", "rumor"])
def test_on_refuses_an_unconfirmed_event(confidence: str) -> None:
    features = EventFeatures(kind="public_figure_launch", confidence=confidence)
    assert evaluate_event_gate(features, require_event=True) == (NO_EVENT,)


def test_on_refuses_a_confirmed_but_disallowed_kind() -> None:
    features = EventFeatures(kind="viral_post", confidence="confirmed")
    assert evaluate_event_gate(features, require_event=True) == (NO_EVENT,)
