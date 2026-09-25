"""``obsidian_note_gate`` — T4.93, "Obsidian primeiro": no audited strategy
change reaches the robots without a note under ``obsidian/`` that covers it.

Everton (owner): "sempre que for usar a estratégia tem que passar analisando
via Obsidian primeiro". The robots never read Obsidian at decision time (a
note is unvalidated text); instead, no change reaches them without a note
that *covers every exact target* — a rule-set ``name/version``, a strategy
``key``/``version`` pair, or a market symbol, matched case-insensitively and
on an identifier boundary against the note's own text. The audited tools call
:func:`gate` right before their one write, never earlier (a refusal for an
unrelated reason, or a no-op that writes nothing, needs no note at all).

``target_groups`` is a sequence of groups, one group per distinct thing the
write touches: the note must mention **at least one spelling from every
group** (OR within a group — e.g. ``"key version"`` and ``"key/version"`` are
two spellings of one strategy version — **AND across groups**, so a batch
``--set-param --all-active`` cannot be justified by a note that only covers
one of several rule sets it changes; the review this caught (Astra, T4.93)
found ``operator/5``'s own note silently covering an unrelated ``flow_v2/6``
in the same batch).

Word-boundary matching (not a bare substring) matters for the same reason:
plain substring search would let a note about ``operator/50`` satisfy a
check for ``operator/5``, and a note about ``volume_anomaly v1`` satisfy a
check for the bare digit ``v1`` alone — both reproduced in review. The
boundary itself treats ``.``/``-`` as identifier characters, not prose
punctuation (a second review round, Astra, T4.93): a note about ``momentum
v1.1`` or ``momentum v2-irma-03`` must not satisfy a check for ``momentum
v1``/``momentum v2`` — version identifiers routinely extend with a dot or a
hyphen, and a bare ``\b`` boundary does not see either as a continuation.

Pure and dependency-free: no database, no network. The git blob sha is
best-effort (``git hash-object --stdin``, cheap — it never touches the
object store) and degrades to ``None`` rather than failing the gate; both
hashes are computed from the exact same bytes read once, so a hash and a
"yes it mentions the target" can never describe two different reads of the
same file (a second review round, Astra, T4.93, found the first cut still
re-read the path for the git hash).
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "NoteProof",
    "NoteRefused",
    "default_repo_root",
    "describe_required_note",
    "gate",
    "provenance_data",
    "provenance_note",
]


class NoteRefused(Exception):
    """One of the named reasons below; ``str(exc)`` is the Portuguese detail."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason


@dataclass(frozen=True, slots=True)
class NoteProof:
    """What ``gate`` read, for the caller to write into its own audit trail."""

    path: str  # relative to repo_root, forward slashes
    sha256: str
    git_blob_sha: str | None


def default_repo_root() -> Path:
    """The repo root, computed from this file's own location
    (``infra/scripts/obsidian_note_gate.py`` -> two parents up)."""
    return Path(__file__).resolve().parents[2]


def _clean_groups(target_groups: Sequence[Sequence[str]]) -> list[list[str]]:
    return [spellings for group in target_groups if (spellings := [t for t in group if t])]


def describe_required_note(target_groups: Sequence[Sequence[str]]) -> str:
    """The dry-run hint: what ``--note`` would need to say to pass ``gate``
    (one spelling per group is enough for a human to search for)."""
    names = " / ".join(group[0] for group in _clean_groups(target_groups))
    return (
        f"para aplicar é preciso --note <arquivo.md sob obsidian/> mencionando {names} "
        "(portão Obsidian primeiro, T4.93)"
    )


def _relative_under_obsidian(note: str) -> Path | None:
    path = Path(note.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        return None
    return path if path.parts and path.parts[0] == "obsidian" else None


def _contained(repo_root: Path, relative: Path) -> Path | None:
    """The resolved file, only if it stays under the resolved ``obsidian/``
    directory — a symlink/junction inside the vault pointing outside it must
    not be able to smuggle arbitrary content in as "the note"."""
    obsidian_root = (repo_root / "obsidian").resolve()
    resolved = (repo_root / relative).resolve()
    return resolved if resolved.is_relative_to(obsidian_root) else None


_WORD_CHAR = r"[A-Za-z0-9_]"
_JOINER_THEN_WORD = r"[./-][A-Za-z0-9_]"
"""A ``.``/``-``/``/`` immediately followed by another word character is an
identifier *continuing* (``v1`` in ``v1.1``, ``v2`` in ``v2-irma-03``) —
reproduced in review (Astra, T4.93): a bare ``\\w`` boundary lets both
through. Punctuation that is *not* followed by a word character (a sentence-
ending period, a comma, a closing paren) is ordinary prose and must not
block an otherwise real mention."""


def _mentions(text_lower: str, target: str) -> bool:
    """Case-insensitive, on an identifier boundary: ``operator/5`` must not
    match inside ``operator/50``, ``v1`` inside ``volume_anomaly v1``, nor
    ``momentum v1`` inside ``momentum v1.1``/``momentum v2-irma-03`` — while
    ``operator/5.`` at the end of a sentence still counts as a real mention."""
    pattern = re.compile(
        rf"(?<!{_WORD_CHAR})(?<!{_WORD_CHAR}[./-])"
        rf"{re.escape(target.lower())}"
        rf"(?!{_WORD_CHAR})(?!{_JOINER_THEN_WORD})"
    )
    return pattern.search(text_lower) is not None


def _git_blob_sha(repo_root: Path, data: bytes) -> str | None:
    """``git hash-object --stdin`` on the exact bytes already read — the blob
    id they would get if staged right now, without touching the object store
    and without a second read of the path (a second review round, Astra,
    T4.93, found ``git hash-object <path>`` re-reading the file, a TOCTOU gap
    against the sha256 computed from the first read). ``None`` on any
    failure (no git, no repo, timeout): never blocks the gate."""
    try:
        result = subprocess.run(
            ["git", "hash-object", "--stdin"],
            cwd=repo_root,
            input=data,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = result.stdout.decode("ascii", errors="replace").strip()
    return sha if result.returncode == 0 and sha else None


def gate(note: str | None, target_groups: Sequence[Sequence[str]], *, repo_root: Path) -> NoteProof:
    """Refuse unless ``note`` is a Markdown file under ``obsidian/`` (relative
    to ``repo_root``) that exists and mentions, on a word boundary, at least
    one spelling from *every* group in ``target_groups``. Call this right
    before the one write an audited act performs — never before an earlier
    refusal or a no-op."""
    groups = _clean_groups(target_groups)
    if not groups:
        raise ValueError("gate() needs at least one target")
    if note is None or not note.strip():
        raise NoteRefused("note_required", describe_required_note(groups))
    relative = _relative_under_obsidian(note.strip())
    if relative is None:
        raise NoteRefused(
            "note_outside_obsidian",
            f"{note!r} precisa ficar sob obsidian/ (caminho relativo à raiz do repositório)",
        )
    resolved = _contained(repo_root, relative)
    if resolved is None:
        raise NoteRefused(
            "note_outside_obsidian",
            f"{relative.as_posix()} escapa de obsidian/ (link fora do cofre)",
        )
    if not resolved.is_file():
        raise NoteRefused("note_missing", f"{relative.as_posix()} não existe")
    if resolved.suffix.lower() != ".md":
        raise NoteRefused("note_not_markdown", f"{relative.as_posix()} não é Markdown (.md)")
    data = resolved.read_bytes()
    lowered = data.decode("utf-8", errors="replace").lower()
    missing = [group for group in groups if not any(_mentions(lowered, t) for t in group)]
    if missing:
        names = " / ".join(group[0] for group in missing)
        raise NoteRefused(
            "note_does_not_mention_target", f"{relative.as_posix()} não menciona {names}"
        )
    return NoteProof(
        path=relative.as_posix(),
        sha256=hashlib.sha256(data).hexdigest(),
        git_blob_sha=_git_blob_sha(repo_root, data),
    )


def provenance_note(proof: NoteProof) -> str:
    """A short bracketed tag for embedding in free text (a ``reason``/``changelog``).

    Truncated for readability — the full hashes are never lost: every caller
    also writes :func:`provenance_data` into a structured column
    (``system_events.data`` / ``meme_rule_set_param_history``) alongside it.
    """
    blob = (proof.git_blob_sha or "indisponivel")[:12]
    return f"[obsidian: {proof.path} sha256={proof.sha256[:12]} git_blob={blob}]"


def provenance_data(proof: NoteProof) -> dict[str, str | None]:
    """The structured form, full hashes, for a ``system_events.data`` (or
    similar) payload."""
    return {
        "note": proof.path,
        "note_sha256": proof.sha256,
        "note_git_blob_sha": proof.git_blob_sha,
    }
