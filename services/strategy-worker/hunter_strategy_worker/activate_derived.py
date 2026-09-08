"""Activate a row whose content was already copied byte for byte (T3.15e).

Pulled out of ``infra/scripts/activate_strategy_version.py`` — same reason
``paper_line.py`` was: the 350-line budget (T3.15). A ``--paper-line`` product
carries its own ``parameters_schema``/``default_parameters``/``params_format``,
copied from the frozen research row it was derived from (D10, "parâmetros
copiados bit a bit"). Activating it must confirm the build still matches the
frozen ``code_ref`` and then write only ``status``, ``activated_at`` and
``changelog`` — never rewrite the copy from today's code, which is what
``activate()``'s plain research path does and what a derived row must not go
through (review T3.15-risk, "Antes de ligar a ponte" item 1).
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from hunter_core.strategies.canonical import params_hash
from hunter_strategy_worker.activation import validate_parameters
from hunter_strategy_worker.activation_db import (
    PURPOSE_RESEARCH_ONLY,
    Refused,
    record_event,
)

__all__ = [
    "DERIVED_RE",
    "LINEAGE_RE",
    "activate_derived",
    "carries_own_content",
    "keep_lineage",
    "parent_version",
    "refuse_rewriting_own_content",
]

LINEAGE_RE = re.compile(
    r"^variante de v\d+ \| derived_from=v\d+ \| overrides=[^|]* \| params_hash=[0-9a-f]{12}"
)
"""The lineage prefix ``infra/scripts/derive_variant.py`` freezes into a variant's
``changelog`` (T3.26). Spelled out here rather than imported because a package
module cannot import from ``infra/scripts`` — the same trade ``catalogue.py``
makes for ``_PURPOSE_LIVE``; a contract test compares the two spellings."""

DERIVED_RE = re.compile(r"^paper line of v\d+|\bderived_from=v\d+\b")
"""A ``changelog`` frozen by a deriving tool — the *fast* path to recognising a
row that carries its own content, spelled out rather than imported (like
``activation_db``'s labels): a guard that fails open is not a guard.

It is a hint, never the proof. ``changelog`` is not frozen by ``0002``'s trigger:
an ``UPDATE`` by hand erases the phrase, and the VPS image published before
``be3674a`` only ever wrote ``paper line of``, so a variant derived by piping
today's script into yesterday's image would not match here at all (review
T3.26-risk, A1). :func:`refuse_rewriting_own_content` is the structural check
that does not depend on any of that."""


_PARENT_RE = re.compile(r"\bderived_from=(v\d+)\b|^paper line of (v\d+)\b")


def parent_version(changelog: str | None) -> str | None:
    """The parent's ``v<n>`` read from a derived row's own frozen ``changelog``.

    ``derived_from=`` wins over ``paper line of`` — the same precedence
    ``obsidian_strategy_pages.parse_parent_version`` applies (T3.26-risk A5), so
    the audit row and the catalogue page can never name two different parents for
    one version.
    """
    match = _PARENT_RE.search(changelog or "")
    return None if match is None else (match.group(1) or match.group(2))


def carries_own_content(row: Any) -> bool:
    """Whether ``row`` is a derived row by its *declared* marks (purpose, phrase)."""
    return (
        row.purpose != PURPOSE_RESEARCH_ONLY or DERIVED_RE.search(row.changelog or "") is not None
    )


def refuse_rewriting_own_content(key: str, version: str, row: Any, params: dict[str, Any]) -> None:
    """Refuse the plain research path for a draft that already has its own set.

    The structural half of the A1 fix. The research path's whole job is to write
    ``default_parameters`` **from today's code** into a row that has none yet —
    that is what a ``seed.py`` draft is. A draft that already carries a non-empty
    set which is *not* the code's own set can only have got it from a deriving
    tool, and rewriting it would silently delete the override and freeze the
    parent's experiment under the variant's version number. Nobody would see it:
    the run prints ``activated``, and the changelog the operator passed replaces
    the lineage that would have explained the difference.

    ``params_hash`` rather than ``==`` because the two sides come from different
    places — JSONB round trip versus ``canonical_json`` of live ``Decimal``s —
    and the hash is exactly the function that already decides whether two
    parameter sets are one experiment (``params_format = 1``).

    Only a draft is checked. An activated row is never rewritten by this path at
    all, and the caller answers it earlier with "already activated".
    """
    frozen: dict[str, Any] = dict(row.default_parameters or {})
    if not frozen or params_hash(frozen) == params_hash(params):
        return
    raise Refused(
        f"{key} {version} is a draft that already carries its own default_parameters "
        f"(params_hash {params_hash(frozen)[:12]}, this build's code is "
        f"{params_hash(params)[:12]}): activating it through the research path would rewrite "
        "them from today's code and freeze the wrong experiment. It was produced by a deriving "
        "tool (derive_variant.py / --paper-line); activate it with a build that recognises it "
        "as derived, or restore the lineage in its changelog"
    )


def keep_lineage(frozen: str | None, changelog: str) -> str:
    """The operator's ``changelog``, with the row's frozen lineage still in front.

    Activation is the only write a derived row ever gets, and it replaces the
    ``changelog`` — which is where ``derived_from=v<n>`` lives, and the only
    thing that ties a variant to its parent for the catalogue exporter
    (``obsidian_strategy_pages.parse_parent_version``). Losing it at activation
    would turn every activated variant into an orphan. A row without the prefix
    (a ``--paper-line`` product, whose lineage the exporter reads from its own
    phrase) is returned untouched.
    """
    match = LINEAGE_RE.match(frozen or "")
    return f"{match.group(0)} | {changelog}" if match else changelog


async def activate_derived(
    conn: AsyncConnection,
    key: str,
    version: str,
    changelog: str,
    row: Any,
    *,
    code_ref: str,
    dry_run: bool,
) -> str:
    """``row`` already carries its own content; ``code_ref`` is what this
    build recomputes for it (the caller resolves the strategy — the same
    resolution :func:`activate` uses for the plain research path)."""
    if row.code_ref != code_ref:
        raise Refused(
            f"{key} {version} is frozen at code_ref {row.code_ref} but this build is "
            f"{code_ref}: deploy the matching build or derive again"
        )
    if row.activated_at is not None:
        return f"{key} {version} was already activated at {row.activated_at.isoformat()}; nothing to do"
    schema: dict[str, Any] = dict(row.parameters_schema or {})
    params: dict[str, Any] = dict(row.default_parameters or {})
    report = validate_parameters(schema, params)
    if not report.ok:
        raise Refused(
            "default_parameters do not match parameters_schema: " + "; ".join(report.errors)
        )
    if dry_run:
        return (
            f"would activate {key} {version} (purpose {row.purpose}) with code_ref {code_ref} "
            f"({len(params)} parameters)"
        )
    kept = keep_lineage(row.changelog, changelog)
    updated = await conn.execute(
        text(
            "UPDATE strategy_versions SET status = 'active', activated_at = now(), "
            "changelog = :changelog WHERE id = :id AND activated_at IS NULL "
            "RETURNING activated_at"
        ),
        {"changelog": kept, "id": row.id},
    )
    activated = updated.first()
    if activated is None:
        raise Refused(f"{key} {version} was activated concurrently; nothing was written")
    # The audit row carries what makes this activation *this experiment* and not
    # another one (T3.26-risk A4): whose content it is (``derived_from``), which
    # content exactly (``params_hash`` of the copy that was activated, not of
    # today's code), and the changelog as it was actually written — lineage
    # prefix included. The operator's note alone dated the event without saying
    # what was dated.
    parent = parent_version(row.changelog)
    await record_event(
        conn,
        "info",
        "strategy_version_activated",
        f"{key} {version} (purpose {row.purpose}) activated with its already-copied "
        f"code_ref={code_ref} params_format={row.params_format} "
        f"derived_from={parent or 'unknown'} params_hash={params_hash(params)} "
        f"changelog={kept!r}",
    )
    return (
        f"activated {key} {version} (purpose {row.purpose}) at {activated[0].isoformat()} "
        f"with code_ref {code_ref}"
    )
