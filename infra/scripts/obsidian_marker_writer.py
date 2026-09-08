"""Marker-preserving writes to one Obsidian page — brief T3.20, item 2.

Everything from the top of the file through ``<!-- generated:end -->`` is
regenerated in full on every run (frontmatter, title, the six body sections);
everything *after* the closing marker is Sexta-feira's — plantão notes, links
she adds by hand, anything — and this module never touches it.

Creates missing pages (with an empty hand-written stub below the markers),
never deletes a page, and refuses instead of guessing when an existing page's
markers are damaged (a human should look at that, not a script).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "GENERATED_END",
    "GENERATED_START",
    "MarkerError",
    "PageDiff",
    "apply_write",
    "plan_write",
]

GENERATED_START = "<!-- generated:start -->"
GENERATED_END = "<!-- generated:end -->"
_DEFAULT_TRAILING = "\n\n\n## Notas\n\n"
"""What a brand-new page gets after the closing marker: the newline that ends
the marker's own line, a blank line, the hand-written stub, a trailing blank
line — the exact shape :func:`_extract_trailing` reads back from an existing
page, so create and update never disagree about where "trailing" starts."""


class MarkerError(RuntimeError):
    """A page exists on disk but is missing its generated markers."""


@dataclass(frozen=True, slots=True)
class PageDiff:
    """What one run would do to one page — printed as-is for ``--dry-run``."""

    path: Path
    action: str
    """``"create"`` | ``"update"`` | ``"unchanged"``."""
    before: str | None
    after: str


def _extract_trailing(existing: str, path: Path) -> str:
    if GENERATED_START not in existing or GENERATED_END not in existing:
        raise MarkerError(
            f"{path}: missing '{GENERATED_START}'/'{GENERATED_END}' markers; "
            "refusing to overwrite a page a human may have hand-written"
        )
    end_index = existing.index(GENERATED_END) + len(GENERATED_END)
    return existing[end_index:]


def plan_write(path: Path, frontmatter: str, title: str, generated_body: str) -> PageDiff:
    """What writing this page would do, without touching disk.

    ``frontmatter`` already ends with a blank line (see the renderer); the
    title is one ``#`` heading. Both are inside the regenerated head, not
    between the markers, because Obsidian frontmatter must open the file.
    """
    existing = path.read_text(encoding="utf-8") if path.exists() else None
    trailing = _DEFAULT_TRAILING if existing is None else _extract_trailing(existing, path)
    # ``head`` stops exactly at the closing marker (no newline of its own):
    # every byte after ``GENERATED_END`` — including the newline that ends its
    # line — belongs to ``trailing``, so a value extracted from disk and the
    # default used for a brand-new page are the same shape and a second run
    # never invents an extra blank line (the idempotency this writer exists for).
    head = f"{frontmatter}# {title}\n\n{GENERATED_START}\n{generated_body}\n{GENERATED_END}"
    after = head + trailing
    if existing is None:
        return PageDiff(path=path, action="create", before=None, after=after)
    if existing == after:
        return PageDiff(path=path, action="unchanged", before=existing, after=after)
    return PageDiff(path=path, action="update", before=existing, after=after)


def apply_write(diff: PageDiff, *, dry_run: bool) -> None:
    """Write ``diff.after`` to disk, unless nothing changed or this is a
    dry run. Never deletes; a page not in this run's roster is left alone."""
    if dry_run or diff.action == "unchanged":
        return
    diff.path.parent.mkdir(parents=True, exist_ok=True)
    diff.path.write_text(diff.after, encoding="utf-8")
