"""Pure classification of the social identity ``/coins/{mint}`` already carries
(T4.26, ``docs/PUMPFUN.md`` §1.3): the ``twitter`` link's kind, its snowflake
post id and instant when it names a post, and a bounded ``description``.

No I/O, no clock other than what the caller passes in — the same discipline
``normalize.py`` holds for every raw-field read of this package.

**Why a post matters** (the plantão's M-P17, ``obsidian/00-INBOX/Hipoteses-do-
plantao.md``): a ``twitter`` link pointing at a *specific post*
(``/status/<snowflake>``) published shortly before the coin's creation is the
strongest public signal that a coin is **news** rather than noise — the
$TRUMP case's own shape. A link to a bare profile or an unrecognized path is
not that signal, and this module never promotes one into the other by guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

TWITTER_EPOCH_MS = 1288834974657
"""X's (Twitter's) own snowflake epoch, ms since Unix epoch — the constant
M-P17 names: ``(id >> 22) + 1288834974657``."""

DESCRIPTION_MAX_CHARS = 2000
TRUNCATION_MARKER = "… [truncated]"

_HOST_RE = re.compile(r"^(?:https?://)?(?:www\.)?(?:twitter\.com|x\.com)/", re.IGNORECASE)
_STATUS_RE = re.compile(r"^([A-Za-z0-9_]{1,15})/status(?:es)?/(\d+)", re.IGNORECASE)
_COMMUNITY_RE = re.compile(r"^i/communities/\d+", re.IGNORECASE)
_PROFILE_RE = re.compile(r"^([A-Za-z0-9_]{1,15})/?$")
_RESERVED_PATHS = frozenset(
    {"i", "home", "explore", "search", "notifications", "messages", "settings", "compose"}
)
"""Twitter's own reserved routes — a bare path matching the handle grammar
that is not actually anyone's handle. Not exhaustive; unknown reserved paths
fall through to ``profile``, which is what a truly unrecognized handle-shaped
string is anyway (this parser never has a users-directory to check against)."""


@dataclass(frozen=True, slots=True)
class TwitterLink:
    """The result of classifying one ``twitter`` field. Immutable, no I/O."""

    kind: str
    post_id: int | None
    post_at: datetime | None


def snowflake_to_instant(snowflake_id: int) -> datetime:
    """X's own formula, exact — ``(id >> 22) + epoch``, milliseconds."""
    ms = (snowflake_id >> 22) + TWITTER_EPOCH_MS
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def classify_twitter_url(url: str | None) -> TwitterLink:
    """``profile`` | ``post`` | ``community`` | ``other`` — never ``None`` for
    a non-empty ``url`` (the caller decides ``twitter_kind IS NULL`` from
    ``url is None`` at the write boundary, not from a value this function
    returns).

    A malformed status id (not a plain non-negative integer, or one so large
    it cannot have come from a real snowflake — X's ids fit in 63 bits) reads
    as ``other``: M-P17's own rule, "id malformado ou futuro = desconhecido,
    nunca zero" — never guessed into ``post``.
    """
    if not url or not url.strip():
        return TwitterLink(kind="other", post_id=None, post_at=None)
    path = _HOST_RE.sub("", url.strip())
    path = path.lstrip("/")
    community = _COMMUNITY_RE.match(path)
    if community:
        return TwitterLink(kind="community", post_id=None, post_at=None)
    status = _STATUS_RE.match(path)
    if status:
        try:
            post_id = int(status.group(2))
        except ValueError:
            return TwitterLink(kind="other", post_id=None, post_at=None)
        if post_id < 0 or post_id.bit_length() > 63:
            return TwitterLink(kind="other", post_id=None, post_at=None)
        return TwitterLink(kind="post", post_id=post_id, post_at=snowflake_to_instant(post_id))
    profile = _PROFILE_RE.match(path)
    if profile and profile.group(1).lower() not in _RESERVED_PATHS:
        return TwitterLink(kind="profile", post_id=None, post_at=None)
    return TwitterLink(kind="other", post_id=None, post_at=None)


def truncate_description(description: str | None) -> str | None:
    """≤ :data:`DESCRIPTION_MAX_CHARS`, marker included in the budget — the
    CHECK in ``ddl/meme_social_checks.py`` is the backstop, this is the writer."""
    if description is None:
        return None
    if len(description) <= DESCRIPTION_MAX_CHARS:
        return description
    keep = DESCRIPTION_MAX_CHARS - len(TRUNCATION_MARKER)
    return description[:keep] + TRUNCATION_MARKER


__all__ = [
    "DESCRIPTION_MAX_CHARS",
    "TRUNCATION_MARKER",
    "TWITTER_EPOCH_MS",
    "TwitterLink",
    "classify_twitter_url",
    "snowflake_to_instant",
    "truncate_description",
]
