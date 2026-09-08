"""Renders one strategy-family page (``momentum.md``) — split out of
:mod:`obsidian_strategy_pages` for the 350-line budget, along the seam the
brief itself draws: a version page is "every detail of one diameter", a family
page is "which versions exist and how they turned out".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from obsidian_yaml import yaml_list, yaml_scalar

__all__ = ["FamilyEntry", "build_family_body", "build_family_frontmatter", "extract_latest_result"]


@dataclass(frozen=True, slots=True)
class FamilyEntry:
    version: str
    purpose: str
    status: str
    slug: str
    verdict: str = "-"


_RESULT_RE = re.compile(r"\*\*Result:\*\*\s*\*\*([^*]+)\*\*")


def extract_latest_result(exp_page_text: str) -> str | None:
    """The last ``**Result:** **word**`` in an EXP page — the Shadow Lab shift's
    own spelling (``sexta-feira.md``: "Every metric with its denominator" /
    editorial threshold). ``None`` when the page has no evaluation yet."""
    matches = _RESULT_RE.findall(exp_page_text)
    return matches[-1].strip() if matches else None


def build_family_frontmatter(strategy_key: str, updated: date) -> str:
    lines = [
        "---",
        f"tags: {yaml_list(['estrategia', 'catalogo', strategy_key, 'familia'])}",
        f"strategy: {yaml_scalar(strategy_key)}",
        f"updated: {updated.isoformat()}",
        "---",
        "",
    ]
    return "\n".join(lines)


def build_family_body(strategy_key: str, entries: list[FamilyEntry]) -> str:
    header = "| Versão | Propósito | Status | Veredito | Página |\n|---|---|---|---|---|"
    rows = "\n".join(
        f"| `{e.version}` | `{e.purpose}` | `{e.status}` | {e.verdict} | [[{e.slug}]] |"
        for e in entries
    )
    table = f"{header}\n{rows}" if entries else "Nenhuma versão cadastrada ainda."
    return "\n".join(
        [
            "## Versões",
            "",
            table,
            "",
            "## Ligações",
            "",
            "- Convenção: [[Estrategias/README|Estratégias]]",
        ]
    )
