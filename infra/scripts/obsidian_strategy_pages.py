"""Renders one strategy-version page — pure functions, no I/O, no database, so
the fixtures in ``tests/test_obsidian_strategy_pages.py`` never need Postgres.
The family-page renderer is the sibling module :mod:`obsidian_family_pages`;
both share :mod:`obsidian_yaml` for frontmatter quoting (350-line budget, and
one quoting rule instead of two that could drift).

Everton, 2026-09-08 (brief T3.20): "lembra todas estrategias vao ficar no
obsidian esse e o diferencial gravar cada detalhe cada diametro" — every
parameter's value, type, bounds (the schema fragment's ``pattern``/``enum``)
and description, never just the value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, cast

from obsidian_yaml import yaml_list, yaml_scalar

if TYPE_CHECKING:
    from obsidian_strategy_queries import ActivationEvent, CohortCount

__all__ = [
    "EXP_LINKS_BY_STRATEGY_PURPOSE",
    "ParamInfo",
    "build_parameters",
    "build_version_body",
    "build_version_frontmatter",
    "exp_links_for",
    "parse_parent_version",
    "parse_replication_sibling",
    "sibling_slug_for",
    "slug_for",
]

EXP_LINKS_BY_STRATEGY_PURPOSE: dict[tuple[str, str], tuple[str, ...]] = {
    ("momentum", "research_only"): ("EXP-0001-momentum-v1",),
    ("momentum", "paper"): ("EXP-0005-momentum-paper",),
    ("volume_anomaly", "research_only"): ("EXP-0002-volume-anomaly-v1",),
}
"""Manual, because no page in the vault names its strategy unambiguously (the
volume_anomaly EXP is tagged ``volume``, not ``volume_anomaly``) — updated by
whoever opens a new ``EXP-NNNN`` page, one line, same rule as any other
cross-reference table in this codebase. See ``Estrategias/README.md``."""


def exp_links_for(strategy_key: str, purpose: str) -> tuple[str, ...]:
    return EXP_LINKS_BY_STRATEGY_PURPOSE.get((strategy_key, purpose), ())


def slug_for(strategy_key: str, version: str, purpose: str) -> str:
    """``momentum v2 research_only -> momentum-v2``; ``momentum v3 paper ->
    momentum-v3-paper`` (brief's own examples). A replication sibling never
    goes through this function — see :func:`sibling_slug_for`."""
    suffix = "-paper" if purpose == "paper" else ""
    return f"{strategy_key}-{version}{suffix}"


def sibling_slug_for(strategy_key: str, parent_version: str, k: int) -> str:
    """``momentum-v2-irma-03`` — brief's own example, now backed by the real
    contract: ``docs/plans/REPLICATION.md`` §4 names every sibling's arm
    ``replication:<parent_version_id>:<k>``, ``k`` from 1."""
    return f"{strategy_key}-{parent_version}-irma-{k:02d}"


_SUCCEEDS_RE = re.compile(r"\bsucceeds (v\d+)\b")
_PAPER_LINE_RE = re.compile(r"\bpaper line of (v\d+)\b")
_DERIVED_FROM_RE = re.compile(r"\bderived_from=(v\d+)\b")
_SIBLING_RE = re.compile(r"^replication:[0-9a-fA-F-]+:(\d+) \| irm[aã] \d+ de (v\d+)\b")


def parse_replication_sibling(changelog: str | None) -> tuple[str, int] | None:
    """``(parent_version, k)`` when ``changelog`` is a replication sibling's own
    frozen label — the exact prefix ``replicate_strategy_version.py`` writes
    (``arm_label`` + its own ``_changelog``: ``"replication:<parent_id>:<k> |
    irmã <k> de <parent_version> (T3.19, docs/plans/REPLICATION.md) | ..."``).
    ``None`` for every other version (T3.19's contract does not exist until
    this pattern actually appears in a real row)."""
    if changelog is None:
        return None
    match = _SIBLING_RE.match(changelog)
    return (match.group(2), int(match.group(1))) if match else None


def parse_parent_version(changelog: str | None) -> str | None:
    """The parent's ``version`` label from a frozen ``changelog`` string, or
    ``None`` for a version with no parent (a first activation).

    Recognises exactly four frozen spellings: ``activate_strategy_version.py``'s
    ``supersede`` and ``--paper-line``, ``replicate_strategy_version.py``'s
    sibling label, and ``derive_variant.py``'s ``derived_from=v<n>`` (T3.26 — the
    only one that is an explicit key rather than a phrase, and the only one that
    survives the variant's own activation, because ``activate_derived`` keeps the
    lineage prefix in front of the operator's note). Anything else is a first
    activation or hand-written prose, and guessing a parent from free text would
    invent a link nobody asked for."""
    if changelog is None:
        return None
    sibling = parse_replication_sibling(changelog)
    if sibling is not None:
        return sibling[0]
    match = (
        _SUCCEEDS_RE.search(changelog)
        or _PAPER_LINE_RE.search(changelog)
        or _DERIVED_FROM_RE.search(changelog)
    )
    return match.group(1) if match else None


@dataclass(frozen=True, slots=True)
class ParamInfo:
    name: str
    value: str
    type: str
    bounds: str
    description: str


def _type_text(fragment: dict[str, Any]) -> str:
    kind = fragment.get("type")
    if isinstance(kind, list):
        items = cast("list[Any]", kind)
        return " | ".join(str(item) for item in items)
    return str(kind) if kind is not None else "-"


def _bounds_text(fragment: dict[str, Any]) -> str:
    if "enum" in fragment:
        return "um de: " + ", ".join(str(item) for item in fragment["enum"])
    if "pattern" in fragment:
        return f"regex `{fragment['pattern']}`"
    return "-"


def build_parameters(schema: dict[str, Any], defaults: dict[str, Any]) -> list[ParamInfo]:
    """Every parameter this version freezes — "cada diametro": value, type,
    bounds and description, sorted by name for a deterministic table.

    Keys come from the union of schema and defaults, not either alone: a
    version whose two disagree (should never happen under
    ``additionalProperties: false``, but nothing here trusts that blindly) is
    shown in full instead of silently dropping the mismatched key."""
    properties: dict[str, Any] = dict(schema.get("properties") or {})
    names = sorted(set(properties) | set(defaults))
    rows: list[ParamInfo] = []
    for name in names:
        fragment = dict(properties.get(name) or {})
        value = defaults[name] if name in defaults else "(ausente)"
        rows.append(
            ParamInfo(
                name=name,
                value=str(value),
                type=_type_text(fragment) if fragment else "(fora do schema)",
                bounds=_bounds_text(fragment),
                description=str(fragment.get("description", "-")),
            )
        )
    return rows


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""


def build_version_frontmatter(
    *,
    strategy_key: str,
    version: str,
    purpose: str,
    status: str,
    code_ref: str | None,
    params_hash: str,
    activated_at: datetime | None,
    deprecated_at: datetime | None,
    derived_from_slug: str | None,
    cohorts: list[str],
    exp_links: tuple[str, ...],
    updated: date,
) -> str:
    derived_from = f"[[{derived_from_slug}]]" if derived_from_slug else ""
    exp = [f"[[{name}]]" for name in exp_links]
    lines = [
        "---",
        f"tags: {yaml_list(['estrategia', 'catalogo', strategy_key])}",
        f"strategy: {yaml_scalar(strategy_key)}",
        f"version: {yaml_scalar(version)}",
        f"purpose: {yaml_scalar(purpose)}",
        f"status: {yaml_scalar(status)}",
        f"code_ref: {yaml_scalar(code_ref)}",
        f"params_hash: {yaml_scalar(params_hash)}",
        f"activated_at: {yaml_scalar(_iso(activated_at))}",
        f"deprecated_at: {yaml_scalar(_iso(deprecated_at))}",
        f"derived_from: {yaml_scalar(derived_from)}",
        f"cohorts: {yaml_list(cohorts)}",
        f"exp: {yaml_list(exp)}",
        f"updated: {updated.isoformat()}",
        "---",
        "",
    ]
    return "\n".join(lines)


def _cell(text: str) -> str:
    """Escapes a literal ``|`` (the "string | number" type text has one) so it
    never gets read as a Markdown table column separator."""
    return text.replace("|", r"\|")


def _parameters_table(params: list[ParamInfo]) -> str:
    if not params:
        return (
            "Nenhum parâmetro definido ainda — versão `draft`, aguardando código "
            "e especificação (`parameters_schema` vazio)."
        )
    header = "| Parâmetro | Valor | Tipo | Vínculo | Descrição |\n|---|---|---|---|---|"
    rows = "\n".join(
        f"| `{p.name}` | `{_cell(p.value)}` | {_cell(p.type)} | {_cell(p.bounds)} | {_cell(p.description)} |"
        for p in params
    )
    return f"{header}\n{rows}"


def _origin_section(changelog: str | None, events: list[ActivationEvent]) -> str:
    changelog_line = (
        f"**Changelog congelado:** {changelog}"
        if changelog
        else "**Changelog congelado:** (nenhum)"
    )
    if not events:
        events_text = "Nenhum evento de ativação registrado ainda (versão nunca ativada)."
    else:
        events_text = "\n".join(
            f"- **{event.created_at.isoformat()}** — `{event.event}` ({event.level}): {event.message}"
            for event in events
        )
    return f"{changelog_line}\n\n{events_text}"


def _cohorts_section(cohorts: list[CohortCount]) -> str:
    if not cohorts:
        return "Nenhum sinal emitido ainda."
    header = "| Coorte | Sinais (`agent_signals`) |\n|---|---|"
    rows = "\n".join(f"| `{_cell(c.cohort)}` | {c.count} |" for c in cohorts)
    total = sum(c.count for c in cohorts)
    return f"{header}\n{rows}\n| **total** | **{total}** |"


def _evaluations_section(exp_links: tuple[str, ...]) -> str:
    if not exp_links:
        return (
            "Nenhuma página de experimento vinculada ainda — abrir um `EXP-NNNN` "
            "quando a coleta começar."
        )
    bullets = "\n".join(f"- [[{name}]]" for name in exp_links)
    return (
        "As avaliações datadas ficam nas páginas de experimento, nunca duplicadas aqui:\n\n"
        + bullets
    )


def _replication_section(replication_status: str | None) -> str:
    return replication_status or (
        "não iniciada — ver `docs/plans/REPLICATION.md` quando existir (T3.19)."
    )


def _links_section(
    *,
    family_slug: str,
    derived_from_slug: str | None,
    sibling_slugs: tuple[str, ...],
    exp_links: tuple[str, ...],
    purpose: str,
) -> str:
    bullets = [f"- Família: [[{family_slug}]]"]
    if derived_from_slug:
        bullets.append(f"- Versão anterior: [[{derived_from_slug}]]")
    if sibling_slugs:
        bullets.append("- Irmãs: " + ", ".join(f"[[{s}]]" for s in sibling_slugs))
    for name in exp_links:
        bullets.append(f"- Experimento: [[{name}]]")
    if purpose == "paper":
        bullets.append("- Risk Engine: [[Risk Engine]]")
    return "\n".join(bullets)


def build_version_body(
    *,
    strategy_key: str,
    version: str,
    purpose: str,
    changelog: str | None,
    params: list[ParamInfo],
    events: list[ActivationEvent],
    cohorts: list[CohortCount],
    exp_links: tuple[str, ...],
    replication_status: str | None,
    derived_from_slug: str | None,
    sibling_slugs: tuple[str, ...] = (),
) -> str:
    """The markdown between the markers — no frontmatter, no title."""
    family_slug = strategy_key
    sections = [
        "## Parâmetros",
        "",
        _parameters_table(params),
        "",
        "## Origem",
        "",
        _origin_section(changelog, events),
        "",
        "## Coortes e sinais",
        "",
        _cohorts_section(cohorts),
        "",
        "## Avaliações",
        "",
        _evaluations_section(exp_links),
        "",
        "## Replicação",
        "",
        _replication_section(replication_status),
        "",
        "## Ligações",
        "",
        _links_section(
            family_slug=family_slug,
            derived_from_slug=derived_from_slug,
            sibling_slugs=sibling_slugs,
            exp_links=exp_links,
            purpose=purpose,
        ),
    ]
    return "\n".join(sections)
