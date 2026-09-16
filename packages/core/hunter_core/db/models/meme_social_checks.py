"""``meme_tokens``'s social identity CHECKs (``0041_meme_social``, T4.26) — split
out of ``meme.py`` for the 350-line budget, the same cut the guards of
``0024``/``0036`` took elsewhere. Appended to ``MemeToken.__table_args__``.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint

TWITTER_KINDS = ("profile", "post", "community", "other")
"""``profile``: a bare handle. ``post``: ``/status/<snowflake>`` (M-P17's
"post específico"). ``community``: ``/i/communities/<id>``. ``other``: a
recognized ``twitter``/``x.com`` link this parser cannot classify further
(a malformed status id, a search, a hashtag) — never ``NULL`` for a present
link, and never guessed into ``post``."""

SOCIAL_SOURCES = ("pumpfun_rest", "indexer_rest", "metadata_uri")
DESCRIPTION_MAX_CHARS = 2000

SOCIAL_CHECKS_0041: tuple[CheckConstraint, ...] = (
    CheckConstraint(
        "(twitter IS NULL) = (twitter_kind IS NULL)",
        name="a_twitter_link_names_its_kind",
    ),
    CheckConstraint(
        f"twitter_kind IS NULL OR twitter_kind IN {TWITTER_KINDS!r}",
        name="twitter_kind_is_a_known_label",
    ),
    CheckConstraint(
        "(twitter_kind = 'post') = (twitter_post_id IS NOT NULL)",
        name="a_post_link_names_its_id",
    ),
    CheckConstraint(
        "(twitter_post_id IS NULL) = (twitter_post_at IS NULL)",
        name="a_post_id_names_its_time",
    ),
    CheckConstraint(
        "twitter_post_id IS NULL OR twitter_post_id >= 0",
        name="twitter_post_id_is_a_snowflake",
    ),
    CheckConstraint(
        "(twitter_reuse_count IS NULL) = (twitter_reuse_observed_at IS NULL)",
        name="a_twitter_reuse_count_names_its_time",
    ),
    CheckConstraint(
        "twitter_reuse_count IS NULL OR twitter_reuse_count >= 0",
        name="twitter_reuse_count_is_not_negative",
    ),
    CheckConstraint(
        "(social_observed_at IS NULL) = (social_source IS NULL)",
        name="a_social_read_names_its_source",
    ),
    CheckConstraint(
        f"social_source IS NULL OR social_source IN {SOCIAL_SOURCES!r}",
        name="social_source_is_a_known_label",
    ),
    CheckConstraint(
        f"description IS NULL OR char_length(description) <= {DESCRIPTION_MAX_CHARS}",
        name="description_is_bounded",
    ),
    CheckConstraint(
        "(twitter IS NULL OR char_length(twitter) > 0) "
        "AND (telegram IS NULL OR char_length(telegram) > 0) "
        "AND (website IS NULL OR char_length(website) > 0) "
        "AND (description IS NULL OR char_length(description) > 0)",
        name="social_identity_is_not_empty",
    ),
)

__all__ = ["DESCRIPTION_MAX_CHARS", "SOCIAL_CHECKS_0041", "SOCIAL_SOURCES", "TWITTER_KINDS"]
