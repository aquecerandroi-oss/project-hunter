"""``hunter_indicators.meme.identity`` — T4.26's cross-cutting identity block:
diagnostic by default, one optional refusal (``no_twitter``)."""

from __future__ import annotations

import pytest

from hunter_indicators.meme.identity import NO_TWITTER, IdentityFeatures, evaluate_identity_gate

pytestmark = pytest.mark.unit


def _features(**overrides: object) -> IdentityFeatures:
    base: dict[str, object] = {
        "has_twitter": False,
        "twitter_kind": None,
        "twitter_post_age_s": None,
        "twitter_reuse_count": None,
        "has_website": False,
        "has_telegram": False,
        "description_len": None,
    }
    base.update(overrides)
    return IdentityFeatures(**base)  # type: ignore[arg-type]


def test_off_by_default_never_refuses_over_an_absent_twitter() -> None:
    assert evaluate_identity_gate(_features(has_twitter=False), require_twitter=False) == ()


def test_on_refuses_a_mint_with_no_twitter() -> None:
    assert evaluate_identity_gate(_features(has_twitter=False), require_twitter=True) == (
        NO_TWITTER,
    )


def test_on_passes_a_mint_with_any_twitter_link() -> None:
    for kind in ("profile", "post", "community", "other"):
        assert (
            evaluate_identity_gate(
                _features(has_twitter=True, twitter_kind=kind), require_twitter=True
            )
            == ()
        )
