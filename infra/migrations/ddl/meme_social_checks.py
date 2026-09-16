"""``meme_tokens``'s social identity CHECKs (``0041_meme_social``, T4.26) — the
literal SQL twin of ``hunter_core.db.models.meme_social_checks``, split out of
``ddl/meme_social.py`` for the 350-line budget. Names match the ORM's naming
convention (``ck_%(table_name)s_%(constraint_name)s``) exactly, so ``alembic
check`` sees the two as one constraint, not a drift.
"""

from __future__ import annotations

TWITTER_KINDS = ("profile", "post", "community", "other")
SOCIAL_SOURCES = ("pumpfun_rest", "indexer_rest", "metadata_uri")
DESCRIPTION_MAX_CHARS = 2000


def _labels(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


CHECK_NAMES_0041: tuple[str, ...] = (
    "ck_meme_tokens_a_twitter_link_names_its_kind",
    "ck_meme_tokens_twitter_kind_is_a_known_label",
    "ck_meme_tokens_a_post_link_names_its_id",
    "ck_meme_tokens_a_post_id_names_its_time",
    "ck_meme_tokens_twitter_post_id_is_a_snowflake",
    "ck_meme_tokens_a_twitter_reuse_count_names_its_time",
    "ck_meme_tokens_twitter_reuse_count_is_not_negative",
    "ck_meme_tokens_a_social_read_names_its_source",
    "ck_meme_tokens_social_source_is_a_known_label",
    "ck_meme_tokens_description_is_bounded",
    "ck_meme_tokens_social_identity_is_not_empty",
)

CHECKS_0041: tuple[str, ...] = (
    "ALTER TABLE meme_tokens ADD CONSTRAINT ck_meme_tokens_a_twitter_link_names_its_kind "
    "CHECK ((twitter IS NULL) = (twitter_kind IS NULL))",
    "ALTER TABLE meme_tokens ADD CONSTRAINT ck_meme_tokens_twitter_kind_is_a_known_label "
    f"CHECK (twitter_kind IS NULL OR twitter_kind IN ({_labels(TWITTER_KINDS)}))",
    "ALTER TABLE meme_tokens ADD CONSTRAINT ck_meme_tokens_a_post_link_names_its_id "
    "CHECK ((twitter_kind = 'post') = (twitter_post_id IS NOT NULL))",
    "ALTER TABLE meme_tokens ADD CONSTRAINT ck_meme_tokens_a_post_id_names_its_time "
    "CHECK ((twitter_post_id IS NULL) = (twitter_post_at IS NULL))",
    "ALTER TABLE meme_tokens ADD CONSTRAINT ck_meme_tokens_twitter_post_id_is_a_snowflake "
    "CHECK (twitter_post_id IS NULL OR twitter_post_id >= 0)",
    "ALTER TABLE meme_tokens ADD CONSTRAINT ck_meme_tokens_a_twitter_reuse_count_names_its_time "
    "CHECK ((twitter_reuse_count IS NULL) = (twitter_reuse_observed_at IS NULL))",
    "ALTER TABLE meme_tokens ADD CONSTRAINT ck_meme_tokens_twitter_reuse_count_is_not_negative "
    "CHECK (twitter_reuse_count IS NULL OR twitter_reuse_count >= 0)",
    "ALTER TABLE meme_tokens ADD CONSTRAINT ck_meme_tokens_a_social_read_names_its_source "
    "CHECK ((social_observed_at IS NULL) = (social_source IS NULL))",
    "ALTER TABLE meme_tokens ADD CONSTRAINT ck_meme_tokens_social_source_is_a_known_label "
    f"CHECK (social_source IS NULL OR social_source IN ({_labels(SOCIAL_SOURCES)}))",
    "ALTER TABLE meme_tokens ADD CONSTRAINT ck_meme_tokens_description_is_bounded "
    f"CHECK (description IS NULL OR char_length(description) <= {DESCRIPTION_MAX_CHARS})",
    "ALTER TABLE meme_tokens ADD CONSTRAINT ck_meme_tokens_social_identity_is_not_empty CHECK ("
    "(twitter IS NULL OR char_length(twitter) > 0) "
    "AND (telegram IS NULL OR char_length(telegram) > 0) "
    "AND (website IS NULL OR char_length(website) > 0) "
    "AND (description IS NULL OR char_length(description) > 0))",
)

__all__ = [
    "CHECKS_0041",
    "CHECK_NAMES_0041",
    "DESCRIPTION_MAX_CHARS",
    "SOCIAL_SOURCES",
    "TWITTER_KINDS",
]
