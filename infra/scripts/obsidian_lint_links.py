#!/usr/bin/env python3
"""Descoberta de arquivos, resolução de ``[[wikilinks]]`` e notas órfãs.

Resolve como o Obsidian resolve, e não por igualdade exata de caminho: um alvo
casa se for o caminho inteiro do arquivo, o nome do arquivo, ou **qualquer
sufixo de caminho em fronteira de barra** (``[[Dialogos/M3]]`` encontra
``06-DECISIONS/Dialogos/M3.md``). ``.base`` e ``.canvas`` entram no índice de
alvos — são arquivos linkáveis da base, ainda que não sejam notas.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

from obsidian_lint_rules import Finding, Note

# Extensões linkáveis que não são notas: entram como alvo, nunca são checadas
# por frontmatter nem cobradas como órfãs.
ASSET_SUFFIXES = frozenset({".base", ".canvas"})

FENCE_RE = re.compile(r"^\s*```")
CODE_SPAN_RE = re.compile(r"`[^`]*`")
WIKILINK_RE = re.compile(r"!?\[\[([^\]]+)\]\]")


class LinkRef(NamedTuple):
    line: int
    target: str


class LinkIndex(NamedTuple):
    """``suffixes`` mapeia todo sufixo de caminho -> caminhos que o satisfazem;
    ``exact`` mapeia as chaves inteiras, que têm preferência sobre o sufixo."""

    suffixes: dict[str, list[str]]
    exact: dict[str, list[str]]


def _is_hidden(root: Path, path: Path) -> bool:
    return any(part.startswith(".") for part in path.relative_to(root).parts)


def discover_notes(root: Path) -> list[Note]:
    return [
        Note(path.relative_to(root).as_posix(), path, path.read_text(encoding="utf-8"))
        for path in sorted(root.rglob("*.md"))
        if not _is_hidden(root, path)
    ]


def discover_assets(root: Path) -> list[str]:
    """Caminhos relativos de ``.base``/``.canvas`` — alvos linkáveis, não notas."""
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.suffix in ASSET_SUFFIXES and not _is_hidden(root, path)
    )


def link_keys(rel_path: str) -> list[str]:
    """Formas pelas quais o Obsidian nomeia um arquivo num ``[[link]]``.

    Para notas, com e sem a extensão ``.md``; para os demais arquivos, só com a
    extensão (``[[Experimentos.base]]``), que é como o Obsidian os referencia.
    """
    if rel_path.endswith(".md"):
        return [rel_path[: -len(".md")], rel_path]
    return [rel_path]


def build_index(rel_paths: list[str]) -> LinkIndex:
    suffixes: dict[str, list[str]] = {}
    exact: dict[str, list[str]] = {}
    for rel_path in rel_paths:
        for key in link_keys(rel_path):
            exact.setdefault(key, []).append(rel_path)
            parts = key.split("/")
            for i in range(len(parts)):
                bucket = suffixes.setdefault("/".join(parts[i:]), [])
                if rel_path not in bucket:
                    bucket.append(rel_path)
    return LinkIndex(suffixes, exact)


def resolve_target(target: str, index: LinkIndex) -> tuple[str, str | None, list[str]]:
    """``("resolved", rel_path, [])`` | ``("ambiguous", None, candidatos)`` | ``("dead", ...)``."""
    for candidates in (index.exact.get(target, []), index.suffixes.get(target, [])):
        unique = list(dict.fromkeys(candidates))
        if len(unique) == 1:
            return "resolved", unique[0], []
        if unique:
            return "ambiguous", None, unique
    return "dead", None, []


def extract_links(text: str) -> list[LinkRef]:
    links: list[LinkRef] = []
    in_fence = False
    for line_no, line in enumerate(text.splitlines(), start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        clean = CODE_SPAN_RE.sub("", line)
        for match in WIKILINK_RE.finditer(clean):
            # Dentro de tabelas o alias vem escapado (``[[Nota\|texto]]``): o
            # ``\|`` é sintaxe de tabela, não parte do nome do arquivo.
            body = match.group(1).replace("\\|", "|")
            target = body.split("|", 1)[0].split("#", 1)[0].strip()
            if target:
                links.append(LinkRef(line_no, target))
    return links


def check_links(
    notes: list[Note], index: LinkIndex
) -> tuple[list[Finding], list[Finding], set[str]]:
    mortos: list[Finding] = []
    ambiguos: list[Finding] = []
    inbound: set[str] = set()
    for note in notes:
        for link in extract_links(note.text):
            kind, target, candidates = resolve_target(link.target, index)
            key = f"{note.rel_path} -> {link.target}"
            if kind == "resolved" and target is not None:
                inbound.add(target)
            elif kind == "dead":
                detalhe = f"alvo inexistente: [[{link.target}]]"
                mortos.append(Finding("links_mortos", note.rel_path, link.line, detalhe, key))
            else:
                detalhe = f"alvo ambíguo [[{link.target}]] — candidatos: {', '.join(candidates)}"
                ambiguos.append(Finding("links_ambiguos", note.rel_path, link.line, detalhe, key))
    return mortos, ambiguos, inbound


def check_orphans(notes: list[Note], inbound: set[str]) -> list[Finding]:
    return [
        Finding("orfas", n.rel_path, 1, "nenhuma outra nota referencia esta página", n.rel_path)
        for n in notes
        if n.rel_path != "00-HOME.md" and n.rel_path not in inbound
    ]
