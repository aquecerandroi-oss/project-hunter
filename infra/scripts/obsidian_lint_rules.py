#!/usr/bin/env python3
"""Regras de frontmatter, vocabulário e append-only do linter da base Obsidian.

Este módulo não tem CLI: o ponto de entrada é ``infra/scripts/obsidian_lint.py``
e a descoberta de arquivos/links vive em ``obsidian_lint_links.py``.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Iterable
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from typing import NamedTuple

COMMON_KEYS = frozenset({"tags", "status", "owner", "updated"})
DATE_KEYS = frozenset({"updated", "opened", "closed", "decided_on", "lido_em"})
INT_KEYS = frozenset({"evaluable", "days"})
ENUM_VOCAB: dict[str, frozenset[str]] = {
    "result": frozenset({"inconclusivo", "validada", "reprovada", "nao-iniciado"}),
    "confiança": frozenset({"anedótico", "backtest do autor", "estudo revisado", "replicado", "?"}),
    "severity": frozenset({"CRITICAL", "HIGH", "MEDIUM", "LOW", "misto"}),
}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
INT_RE = re.compile(r"^\d+$")
KEY_RE = re.compile(r"^([^\s:#][^:]*):(.*)$")
HEADING_RE = re.compile(r"^### Avaliação de ")
BOUNDARY_RE = re.compile(r"^#{2,3} ")
ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
VERSION_SUFFIX_RE = re.compile(r"-v\d")


class Note(NamedTuple):
    """Uma nota Markdown da base (só ``.md``; `.base`/`.canvas` são alvos, não notas)."""

    rel_path: str
    abs_path: Path
    text: str


class Finding(NamedTuple):
    categoria: str
    arquivo: str
    linha: int
    detalhe: str
    allow_key: str


class Section(NamedTuple):
    heading: str
    body: str
    line: int


FrontMatter = dict[str, tuple[str, int]]


def _unquote(value: str) -> str:
    s = value.strip()
    return s[1:-1] if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'" else s


def parse_frontmatter(text: str) -> FrontMatter:
    """Top-level ``key: (raw_value, line_number)`` of a leading ``---`` block, no PyYAML."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}

    result: FrontMatter = {}
    i = 1
    while i < end:
        match = KEY_RE.match(lines[i])
        if match is None:
            i += 1
            continue
        key = match.group(1).strip()
        rest = match.group(2)
        value = (rest[1:] if rest.startswith(" ") else rest).strip()
        line_no = i + 1
        if value == "":
            j = i + 1
            has_list = False
            while j < end and (lines[j].startswith(" ") or lines[j].startswith("\t")):
                has_list = has_list or lines[j].strip().startswith("-")
                j += 1
            result[key] = ("<lista>" if has_list else "", line_no)
            i = j if has_list else i + 1
            continue
        result[key] = (value, line_no)
        i += 1
    return result


def is_template(rel_path: str) -> bool:
    """Templates declaram as chaves com valor vazio de propósito — presença basta."""
    return PurePosixPath(rel_path).name.startswith("_TEMPLATE-")


def required_keys(rel_path: str) -> set[str]:
    name = PurePosixPath(rel_path).name
    stem = PurePosixPath(rel_path).stem
    if rel_path.startswith("03-TRADING/Estrategias/"):
        # README.md é a convenção do catálogo (T3.20), não uma página de estratégia.
        if name == "README.md":
            return {"tags", "updated"}
        keys = {"tags", "strategy", "updated"}
        if VERSION_SUFFIX_RE.search(stem):
            keys |= {"version", "purpose", "status", "code_ref", "params_hash"}
        return keys
    if rel_path.startswith("05-EXPERIMENTS/") and (
        fnmatch(name, "EXP-*.md") or name == "_TEMPLATE-EXP.md"
    ):
        return set(COMMON_KEYS) | {"exp", "strategy", "version", "result", "evaluable", "days"}
    if rel_path.startswith("07-BUGS/") and "/" not in rel_path[len("07-BUGS/") :]:
        return set(COMMON_KEYS) | {"severity", "opened", "closed"}
    if rel_path.startswith("06-DECISIONS/"):
        return set(COMMON_KEYS) | {"decided_on", "by"}
    if rel_path.startswith("11-KNOWLEDGE/") and (
        fnmatch(name, "KB-*.md") or name == "_TEMPLATE-NOTE.md"
    ):
        return set(COMMON_KEYS) | {"fonte", "lido_em", "confiança"}
    return set(COMMON_KEYS)


def _missing(frontmatter: FrontMatter, keys: Iterable[str], *, presence_only: bool) -> list[str]:
    if presence_only:
        return sorted(k for k in keys if k not in frontmatter)
    return sorted(k for k in keys if k not in frontmatter or frontmatter[k][0] == "")


def check_frontmatter(notes: list[Note]) -> tuple[list[Finding], dict[str, FrontMatter]]:
    findings: list[Finding] = []
    parsed: dict[str, FrontMatter] = {}
    for note in notes:
        frontmatter = parse_frontmatter(note.text)
        parsed[note.rel_path] = frontmatter
        missing = _missing(
            frontmatter, required_keys(note.rel_path), presence_only=is_template(note.rel_path)
        )
        if missing:
            detalhe = "faltam: " + ", ".join(missing)
            findings.append(Finding("frontmatter", note.rel_path, 1, detalhe, note.rel_path))
    return findings, parsed


def check_values(notes: list[Note], parsed: dict[str, FrontMatter]) -> list[Finding]:
    findings: list[Finding] = []
    for note in notes:
        for key, (raw, line) in parsed.get(note.rel_path, {}).items():
            value = _unquote(raw)
            if value == "":
                continue
            bad = (
                (key in DATE_KEYS and not DATE_RE.match(value))
                or (key in ENUM_VOCAB and value not in ENUM_VOCAB[key])
                or (key in INT_KEYS and not INT_RE.match(value))
            )
            if bad:
                detalhe = f"{key} = {raw!r} fora do vocabulário esperado"
                allow_key = f"{note.rel_path} -> {key}"
                findings.append(Finding("valores", note.rel_path, line, detalhe, allow_key))
    return findings


def check_kb_procedencia(notes: list[Note], parsed: dict[str, FrontMatter]) -> list[Finding]:
    findings: list[Finding] = []
    for note in notes:
        name = PurePosixPath(note.rel_path).name
        if not note.rel_path.startswith("11-KNOWLEDGE/") or not fnmatch(name, "KB-*.md"):
            continue
        missing = _missing(parsed.get(note.rel_path, {}), ("fonte", "lido_em"), presence_only=False)
        if missing:
            detalhe = "faltam: " + ", ".join(missing)
            findings.append(Finding("kb_procedencia", note.rel_path, 1, detalhe, note.rel_path))
    return findings


def split_sections(text: str) -> dict[str, Section]:
    lines = text.splitlines(keepends=True)
    sections: dict[str, Section] = {}
    heading: str | None = None
    heading_line = 0
    body: list[str] = []
    for idx, line in enumerate(lines, start=1):
        if HEADING_RE.match(line):
            if heading is not None:
                sections[heading] = Section(heading, "".join(body), heading_line)
            heading, heading_line, body = line.rstrip("\n"), idx, []
        elif BOUNDARY_RE.match(line) and heading is not None:
            sections[heading] = Section(heading, "".join(body), heading_line)
            heading, body = None, []
        elif heading is not None:
            body.append(line)
    if heading is not None:
        sections[heading] = Section(heading, "".join(body), heading_line)
    return sections


def check_exp_rewrite(
    note: Note, read_head_text: Callable[[Path], str | None]
) -> tuple[list[Finding], bool]:
    committed = read_head_text(note.abs_path)
    if committed is None:
        return [], False
    committed_sections = split_sections(committed)
    working_sections = split_sections(note.text)
    findings: list[Finding] = []
    for heading, section in committed_sections.items():
        if not ISO_DATE_RE.search(heading):
            continue
        current = working_sections.get(heading)
        title = heading.lstrip("#").strip()
        allow_key = f"{note.rel_path} -> {heading}"
        if current is None:
            detalhe = f"seção removida ou renomeada (viola append-only): {title}"
            findings.append(Finding("exp_reescrita", note.rel_path, 1, detalhe, allow_key))
        elif current.body != section.body:
            detalhe = f"seção reescrita (viola append-only): {title}"
            findings.append(
                Finding("exp_reescrita", note.rel_path, current.line, detalhe, allow_key)
            )
    return findings, True


def find_repo_root(start: Path) -> Path | None:
    current = start.resolve()
    return next((c for c in (current, *current.parents) if (c / ".git").exists()), None)


def is_git_available() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def make_git_reader(repo_root: Path) -> Callable[[Path], str | None]:
    def _read(abs_path: Path) -> str | None:
        try:
            rel = abs_path.resolve().relative_to(repo_root).as_posix()
        except ValueError:
            return None
        try:
            result = subprocess.run(
                ["git", "show", f"HEAD:{rel}"],
                cwd=repo_root,
                capture_output=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return result.stdout.decode("utf-8", errors="replace") if result.returncode == 0 else None

    return _read


def run_exp_rewrite_checks(
    notes: list[Note], root: Path, no_git: bool
) -> tuple[list[Finding], list[str]]:
    if no_git:
        return [], ["checagem exp_reescrita desativada (--no-git)."]
    if not is_git_available():
        return [], ["git não encontrado no PATH — checagem exp_reescrita desativada."]
    repo_root = find_repo_root(root)
    if repo_root is None:
        return [], [
            "repositório git não encontrado a partir de --root — checagem exp_reescrita desativada."
        ]

    reader = make_git_reader(repo_root)
    findings: list[Finding] = []
    skipped = 0
    for note in notes:
        name = PurePosixPath(note.rel_path).name
        if not (note.rel_path.startswith("05-EXPERIMENTS/") and fnmatch(name, "EXP-*.md")):
            continue
        note_findings, checked = check_exp_rewrite(note, reader)
        findings.extend(note_findings)
        skipped += 0 if checked else 1
    info = [f"{skipped} experimento(s) fora do HEAD ignorado(s) na checagem append-only."]
    return findings, (info if skipped else [])
