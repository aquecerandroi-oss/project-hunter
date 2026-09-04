"""Organization slugs: derived from the name, validated, always URL-safe.

The slug is a public identifier (it will appear in URLs and in the org
switcher), so it is ASCII, lowercase, and matches :data:`SLUG_PATTERN` — the
same pattern the API validates against, kept in one place so the derivation
can never produce something the validator would reject.
"""

from __future__ import annotations

import re
import secrets
import unicodedata

SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]{2,39}$"
"""3-40 characters, starting alphanumeric. Short enough to type, long enough
for a real company name, and never a bare hyphen."""

SLUG_MAX_LENGTH = 40
_SUFFIX_BYTES = 3
_NON_SLUG = re.compile(r"[^a-z0-9]+")
_slug_re = re.compile(SLUG_PATTERN)


def is_valid_slug(value: str) -> bool:
    return bool(_slug_re.match(value))


def derive_slug(name: str) -> str:
    """A valid slug for ``name``, always.

    Accents are folded (``Ação`` → ``acao``) rather than dropped, so a
    Portuguese name still yields something recognisable. A name that cannot
    produce three usable characters — punctuation only, emoji only, two
    letters — falls back to a random ``org-xxxxxx``: refusing to create the
    organization would be a worse answer than an ugly slug the owner can
    change later.
    """
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    candidate = _NON_SLUG.sub("-", folded.lower()).strip("-")[:SLUG_MAX_LENGTH].strip("-")
    if is_valid_slug(candidate):
        return candidate
    return _random_slug()


def suffixed_slug(base: str) -> str:
    """A distinct slug for a retry after a uniqueness collision.

    Random rather than ``-2``/``-3``: a sequential suffix tells whoever holds
    ``acme`` that ``acme-2`` was just created, and turns the retry loop into a
    scan of how many organizations share a name.
    """
    suffix = f"-{secrets.token_hex(_SUFFIX_BYTES)}"
    trimmed = base[: SLUG_MAX_LENGTH - len(suffix)].strip("-")
    candidate = f"{trimmed}{suffix}" if trimmed else _random_slug()
    return candidate if is_valid_slug(candidate) else _random_slug()


def _random_slug() -> str:
    return f"org-{secrets.token_hex(_SUFFIX_BYTES)}"
