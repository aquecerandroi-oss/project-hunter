from datetime import UTC, datetime

import pytest

from hunter_exchanges.pumpfun.social import (
    DESCRIPTION_MAX_CHARS,
    TRUNCATION_MARKER,
    classify_twitter_url,
    snowflake_to_instant,
    truncate_description,
)


def test_snowflake_decodes_the_measured_mp17_post() -> None:
    """M-P17: CoachPatNFT's post, 13 s before the coin it named was created —
    the plantão read 00:45:19 BRT (03:45:19 UTC) by hand; the formula agrees."""
    assert snowflake_to_instant(2098618936124375364) == datetime(
        2026, 9, 12, 3, 45, 19, 483000, tzinfo=UTC
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://x.com/CoachPatNFT/status/2098618936124375364",
        "http://twitter.com/CoachPatNFT/status/2098618936124375364",
        "x.com/CoachPatNFT/status/2098618936124375364",
        "www.x.com/CoachPatNFT/statuses/2098618936124375364",
    ],
)
def test_classifies_a_post_link_in_every_observed_shape(url: str) -> None:
    link = classify_twitter_url(url)
    assert link.kind == "post"
    assert link.post_id == 2098618936124375364
    assert link.post_at == datetime(2026, 9, 12, 3, 45, 19, 483000, tzinfo=UTC)


def test_classifies_a_bare_handle_as_profile() -> None:
    """The plantão's other two: ``revolve`` (a profile) and the ``Benz``
    graduated coin's brand profile — both bare handles, no post."""
    for url in ("x.com/revolvepad", "https://x.com/MercedesBenz", "x.com/MercedesBenz/"):
        link = classify_twitter_url(url)
        assert link.kind == "profile"
        assert link.post_id is None
        assert link.post_at is None


def test_classifies_a_community_link() -> None:
    link = classify_twitter_url("https://x.com/i/communities/1234567890")
    assert link.kind == "community"
    assert link.post_id is None


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "   ",
        "x.com/a/status/not_a_number",
        "x.com/a/status/-1",
        f"x.com/a/status/{2**63}",
        "x.com/search?q=pump",
    ],
)
def test_classifies_absent_or_unrecognized_or_malformed_as_other(url: str | None) -> None:
    """M-P17's own rule: a malformed or out-of-range status id is ``other``,
    never guessed into ``post`` and never a silent zero."""
    link = classify_twitter_url(url)
    assert link.kind == "other"
    assert link.post_id is None
    assert link.post_at is None


def test_truncate_description_is_a_no_op_under_the_budget() -> None:
    assert truncate_description(None) is None
    assert truncate_description("hello") == "hello"
    assert truncate_description("a" * DESCRIPTION_MAX_CHARS) == "a" * DESCRIPTION_MAX_CHARS


def test_truncate_description_marks_what_it_cuts() -> None:
    truncated = truncate_description("a" * (DESCRIPTION_MAX_CHARS + 500))
    assert truncated is not None
    assert len(truncated) == DESCRIPTION_MAX_CHARS
    assert truncated.endswith(TRUNCATION_MARKER)
