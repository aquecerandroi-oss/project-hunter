#!/usr/bin/env python3
"""Linter somente-leitura (nunca escreve) da base Obsidian do PROJECT HUNTER.

Uso: ``uv run python infra/scripts/obsidian_lint.py [--root obsidian]
[--format text|markdown] [--no-git]``. Saída 0 sem achados fora da
allowlist, 1 caso contrário. Relatório inteiro em português.

As regras vivem em ``obsidian_lint_rules.py`` (frontmatter, vocabulário,
append-only) e em ``obsidian_lint_links.py`` (arquivos, links, órfãs).
"""

from __future__ import annotations

import argparse
import io
import sys
from collections.abc import Sequence
from pathlib import Path

# Módulos irmãos, sem pacote: rodando como script o próprio diretório é
# sys.path[0]; sob pytest o teste insere infra/scripts em sys.path.
from obsidian_lint_links import (
    build_index,
    check_links,
    check_orphans,
    discover_assets,
    discover_notes,
)
from obsidian_lint_rules import (
    Finding,
    check_frontmatter,
    check_kb_procedencia,
    check_values,
    run_exp_rewrite_checks,
)

# (categoria, rótulo em português), na ordem em que aparecem no relatório.
_CATEGORIES = (
    ("links_mortos", "Links mortos"),
    ("links_ambiguos", "Links ambíguos"),
    ("orfas", "Notas órfãs"),
    ("frontmatter", "Frontmatter incompleto"),
    ("valores", "Valores fora do vocabulário"),
    ("kb_procedencia", "Procedência da Knowledge Base (KB-*)"),
    ("exp_reescrita", "Reescrita de experimentos (append-only)"),
)
CATEGORY_ORDER = tuple(categoria for categoria, _ in _CATEGORIES)
CATEGORY_LABELS: dict[str, str] = dict(_CATEGORIES)

# Achados conhecidos que o relatório mostra sem falhar: ``(categoria,
# allow_key)`` -> motivo em português. Vazia desde a T3.21, quando a resolução
# por sufixo passou a encontrar [[Estrategias/README]] de verdade — um item
# aqui é dívida declarada com motivo, nunca um jeito de calar o linter.
ALLOWLIST: dict[tuple[str, str], str] = {}


def render_report(
    by_category: dict[str, list[Finding]],
    allowed: list[tuple[Finding, str]],
    info: list[str],
    total_notes: int,
    fmt: str,
) -> str:
    h = "## " if fmt == "markdown" else ""
    total = sum(len(items) for items in by_category.values())
    title = f"Lint da base Obsidian — {total_notes} nota(s) analisada(s)"
    lines: list[str] = [f"# {title}" if fmt == "markdown" else title.upper()]
    resumo = ", ".join(
        f"{CATEGORY_LABELS[c]}: {len(by_category.get(c, []))}" for c in CATEGORY_ORDER
    )
    lines.append(f"Resumo — {resumo}.")
    lines.extend(f"Info: {line}" for line in info)
    lines.append("")

    for cat in CATEGORY_ORDER:
        items = by_category.get(cat, [])
        if not items:
            continue
        lines.append(f"{h}{CATEGORY_LABELS[cat]} ({len(items)})")
        lines.extend(f"- {f.arquivo}:{f.linha} — {f.detalhe}" for f in items)
        lines.append("")

    if allowed:
        lines.append(f"{h}Conhecidos (com motivo) ({len(allowed)})")
        for finding, reason in allowed:
            label = CATEGORY_LABELS[finding.categoria]
            lines.append(
                f"- [{label}] {finding.arquivo}:{finding.linha} — {finding.detalhe} "
                f"— motivo: {reason}"
            )
        lines.append("")

    lines.append("RESULTADO: base limpa" if total == 0 else f"RESULTADO: {total} achado(s)")
    return "\n".join(lines)


def lint(root: Path, fmt: str, no_git: bool) -> tuple[str, int]:
    notes = discover_notes(root)
    index = build_index([note.rel_path for note in notes] + discover_assets(root))

    mortos, ambiguos, inbound = check_links(notes, index)
    orfas = check_orphans(notes, inbound)
    frontmatter_findings, parsed = check_frontmatter(notes)
    valores_findings = check_values(notes, parsed)
    kb_findings = check_kb_procedencia(notes, parsed)
    exp_findings, info = run_exp_rewrite_checks(notes, root, no_git)

    by_category: dict[str, list[Finding]] = {cat: [] for cat in CATEGORY_ORDER}
    allowed: list[tuple[Finding, str]] = []
    all_findings = (
        *mortos,
        *ambiguos,
        *orfas,
        *frontmatter_findings,
        *valores_findings,
        *kb_findings,
        *exp_findings,
    )
    for finding in all_findings:
        reason = ALLOWLIST.get((finding.categoria, finding.allow_key))
        if reason is not None:
            allowed.append((finding, reason))
        else:
            by_category[finding.categoria].append(finding)

    report = render_report(by_category, allowed, info, len(notes), fmt)
    exit_code = 0 if sum(len(items) for items in by_category.values()) == 0 else 1
    return report, exit_code


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Linter somente-leitura da base Obsidian do PROJECT HUNTER."
    )
    parser.add_argument("--root", default=Path("obsidian"), type=Path)
    parser.add_argument("--format", choices=("text", "markdown"), default="text")
    parser.add_argument("--no-git", action="store_true")
    args = parser.parse_args(argv)

    # Windows consoles default to cp1252; o relatório tem "—", "→" etc.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(  # type: ignore[reportUnknownMemberType]
            encoding="utf-8", errors="replace"
        )

    root: Path = args.root
    if not root.is_dir():
        print(f"Diretório não encontrado: {root}")
        return 1

    report, exit_code = lint(root, args.format, args.no_git)
    print(report)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
