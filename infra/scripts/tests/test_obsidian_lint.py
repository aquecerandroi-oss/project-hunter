"""Unit tests for the read-only Obsidian base linter (T3.21a).

No Docker, no testcontainers, no network — every fixture is a tiny fake
vault built with ``tmp_path``. Run: ``uv run pytest
infra/scripts/tests/test_obsidian_lint.py -q``
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from obsidian_lint import lint  # noqa: E402
from obsidian_lint_links import discover_notes  # noqa: E402
from obsidian_lint_rules import check_exp_rewrite  # noqa: E402


def _write(root: Path, rel_path: str, content: str) -> Path:
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _home(root: Path, links: str = "") -> None:
    """00-HOME.md is exempt from the orphan check; ``links`` keeps other fixture
    notes non-orphan without every test having to reason about inbound links.
    """
    _write(
        root,
        "00-HOME.md",
        "---\ntags: [home]\nstatus: ok\nowner: sexta-feira\nupdated: 2026-09-08\n---\n"
        f"# Home\n\n{links}\n",
    )


def _basic_note(root: Path, rel_path: str, title: str, body: str = "") -> None:
    _write(
        root,
        rel_path,
        f"---\ntags: [nota]\nstatus: ok\nowner: sexta-feira\nupdated: 2026-09-08\n---\n"
        f"# {title}\n\n{body}",
    )


def _section(report: str, label: str) -> str:
    """Body of a "## Label (N)" section — distinct from the "Label: N" summary
    line, which also contains ``label`` and would otherwise confuse a naive split.
    """
    marker = f"{label} ("
    assert marker in report, f"secção {label!r} não encontrada no relatório:\n{report}"
    return report.split(marker, 1)[1]


def _has_section(report: str, label: str) -> bool:
    return f"{label} (" in report


def test_clean_vault_exits_zero_with_base_limpa(tmp_path: Path) -> None:
    _home(tmp_path, "[[Nota A]]")
    _basic_note(tmp_path, "Nota A.md", "Nota A")

    report, exit_code = lint(tmp_path, "text", no_git=True)

    assert exit_code == 0
    assert "RESULTADO: base limpa" in report


def test_dead_link_reports_file_and_line_number(tmp_path: Path) -> None:
    _home(tmp_path, "[[Nota A]]")
    _basic_note(tmp_path, "Nota A.md", "Nota A", body="linha 1\n[[Fantasma]]\n")

    report, exit_code = lint(tmp_path, "text", no_git=True)

    assert exit_code == 1
    assert "Nota A.md:10" in report
    assert "Fantasma" in report
    assert "Links mortos" in report


def test_link_in_fenced_code_block_is_ignored(tmp_path: Path) -> None:
    _home(tmp_path, "[[Nota A]]")
    _basic_note(
        tmp_path,
        "Nota A.md",
        "Nota A",
        body="```\n[[Fantasma]]\n```\n",
    )

    report, exit_code = lint(tmp_path, "text", no_git=True)

    assert exit_code == 0
    assert "Fantasma" not in report


def test_link_in_inline_code_span_is_ignored(tmp_path: Path) -> None:
    _home(tmp_path, "[[Nota A]]")
    _basic_note(tmp_path, "Nota A.md", "Nota A", body="veja `[[Fantasma]]` no texto.\n")

    report, exit_code = lint(tmp_path, "text", no_git=True)

    assert exit_code == 0
    assert "Fantasma" not in report


def test_alias_and_fragment_resolve_to_bare_target(tmp_path: Path) -> None:
    _home(tmp_path, "[[Nota B]]")
    _basic_note(tmp_path, "Nota A.md", "Nota A")
    _basic_note(
        tmp_path,
        "Nota B.md",
        "Nota B",
        body="[[Nota A|texto]] e [[Nota A#Seção]]\n",
    )

    report, exit_code = lint(tmp_path, "text", no_git=True)

    assert exit_code == 0
    assert "RESULTADO: base limpa" in report
    assert not _has_section(report, "Links mortos")


def test_escaped_pipe_alias_in_table_cell_resolves_to_bare_target(tmp_path: Path) -> None:
    """Inside a Markdown table cell the alias separator must be escaped as
    ``\\|`` so it doesn't break the column; Obsidian still resolves the link.
    """
    _home(tmp_path, "[[Nota A]] [[Nota B]]")
    _basic_note(tmp_path, "Nota A.md", "Nota A")
    _basic_note(
        tmp_path,
        "Nota B.md",
        "Nota B",
        body="| x | [[Nota A\\|texto da coluna]] |\n|---|---|\n",
    )

    report, exit_code = lint(tmp_path, "text", no_git=True)

    assert exit_code == 0
    assert "RESULTADO: base limpa" in report
    assert not _has_section(report, "Links mortos")


def test_ambiguous_basename_reported_not_dead(tmp_path: Path) -> None:
    _home(tmp_path)
    _basic_note(tmp_path, "pasta1/Dup.md", "Dup 1")
    _basic_note(tmp_path, "pasta2/Dup.md", "Dup 2")
    _basic_note(tmp_path, "Nota A.md", "Nota A", body="[[Dup]]\n")

    report, exit_code = lint(tmp_path, "text", no_git=True)

    assert exit_code == 1
    assert "Dup" in _section(report, "Links ambíguos")
    assert not _has_section(report, "Links mortos")


def test_orphan_note_reported_and_home_never_orphan(tmp_path: Path) -> None:
    _home(tmp_path, "[[Nota A]]")
    _basic_note(tmp_path, "Nota A.md", "Nota A")
    _basic_note(tmp_path, "Orfa.md", "Orfa")

    report, exit_code = lint(tmp_path, "text", no_git=True)

    assert exit_code == 1
    orphan_section = _section(report, "Notas órfãs").split("RESULTADO")[0]
    assert "Orfa.md" in orphan_section
    assert "Nota A.md" not in orphan_section
    assert "00-HOME.md" not in orphan_section


def test_missing_owner_reported_on_normal_note(tmp_path: Path) -> None:
    _home(tmp_path)
    _write(
        tmp_path,
        "Nota A.md",
        "---\ntags: [nota]\nstatus: ok\nupdated: 2026-09-08\n---\n# Nota A\n[[00-HOME]]\n",
    )

    report, exit_code = lint(tmp_path, "text", no_git=True)

    assert exit_code == 1
    assert "owner" in _section(report, "Frontmatter incompleto")


def test_missing_owner_not_required_for_estrategia_page(tmp_path: Path) -> None:
    _home(tmp_path, "[[momentum]]")
    _write(
        tmp_path,
        "03-TRADING/Estrategias/momentum.md",
        "---\ntags: [estrategia]\nstrategy: momentum\nupdated: 2026-09-08\n---\n"
        "# momentum\n[[00-HOME]]\n",
    )

    report, exit_code = lint(tmp_path, "text", no_git=True)

    assert exit_code == 0
    assert "RESULTADO: base limpa" in report


def test_bad_updated_value_reported_under_valores(tmp_path: Path) -> None:
    _home(tmp_path)
    _write(
        tmp_path,
        "Nota A.md",
        "---\ntags: [nota]\nstatus: ok\nowner: sexta-feira\nupdated: 08/09/2026\n---\n"
        "# Nota A\n[[00-HOME]]\n",
    )

    report, exit_code = lint(tmp_path, "text", no_git=True)

    assert exit_code == 1
    assert "updated" in _section(report, "Valores fora do vocabulário")


def test_confianca_talvez_reported_and_question_mark_accepted(tmp_path: Path) -> None:
    _home(tmp_path)
    _write(
        tmp_path,
        "11-KNOWLEDGE/KB-0001-teste.md",
        "---\ntags: [knowledge]\nstatus: ok\nowner: sexta-feira\nupdated: 2026-09-08\n"
        "fonte: X\nlido_em: 2026-09-08\nconfiança: talvez\n---\n# KB-0001\n[[00-HOME]]\n",
    )

    report, exit_code = lint(tmp_path, "text", no_git=True)

    assert exit_code == 1
    assert "confiança" in _section(report, "Valores fora do vocabulário")

    ok_root = tmp_path / "ok"
    _home(ok_root, "[[KB-0001-teste]]")
    _write(
        ok_root,
        "11-KNOWLEDGE/KB-0001-teste.md",
        "---\ntags: [knowledge]\nstatus: ok\nowner: sexta-feira\nupdated: 2026-09-08\n"
        'fonte: X\nlido_em: 2026-09-08\nconfiança: "?"\n---\n# KB-0001\n[[00-HOME]]\n',
    )
    ok_report, ok_exit_code = lint(ok_root, "text", no_git=True)
    assert ok_exit_code == 0
    assert not _has_section(ok_report, "Valores fora do vocabulário")


def test_kb_note_missing_lido_em_flagged_in_kb_procedencia(tmp_path: Path) -> None:
    _home(tmp_path)
    _write(
        tmp_path,
        "11-KNOWLEDGE/KB-0001-teste.md",
        "---\ntags: [knowledge]\nstatus: ok\nowner: sexta-feira\nupdated: 2026-09-08\n"
        'fonte: X\nconfiança: "?"\n---\n# KB-0001\n[[00-HOME]]\n',
    )

    report, exit_code = lint(tmp_path, "text", no_git=True)

    assert exit_code == 1
    assert "lido_em" in _section(report, "Procedência da Knowledge Base (KB-*)")


def test_allowlist_suppresses_finding_and_keeps_exit_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import obsidian_lint

    _home(tmp_path, "[[Nota A]]")
    _basic_note(tmp_path, "Nota A.md", "Nota A", body="[[Fantasma]]\n")

    monkeypatch.setitem(
        obsidian_lint.ALLOWLIST,
        ("links_mortos", "Nota A.md -> Fantasma"),
        "conhecido, sem correção necessária neste teste",
    )

    report, exit_code = lint(tmp_path, "text", no_git=True)

    assert exit_code == 0
    assert "Fantasma" in _section(report, "Conhecidos (com motivo)")


# -- exp_reescrita (append-only) -----------------------------------------------


def _exp_note(root: Path, sections: str) -> Path:
    return _write(
        root,
        "05-EXPERIMENTS/EXP-0001-teste.md",
        "---\ntags: [experimento]\nstatus: ok\nowner: sexta-feira\nupdated: 2026-09-08\n"
        "exp: EXP-0001\nstrategy: momentum\nversion: v1\nresult: inconclusivo\n"
        f"evaluable: 1\ndays: 1\n---\n# EXP-0001\n[[00-HOME]]\n\n{sections}",
    )


_COMMITTED_SECTIONS = (
    "### Avaliação de 2026-09-06 — turno 1\nconteúdo original, nunca muda.\n\n"
    "### Avaliação de <próxima data>\npreencher quando houver nova leitura.\n"
)


def test_exp_rewrite_changed_dated_section_is_reported(tmp_path: Path) -> None:
    _home(tmp_path)
    note_path = _exp_note(tmp_path, _COMMITTED_SECTIONS)
    committed_text = note_path.read_text(encoding="utf-8")

    changed_text = committed_text.replace("conteúdo original, nunca muda.", "TEXTO ALTERADO.")
    note_path.write_text(changed_text, encoding="utf-8")

    def fake_read_head(_abs_path: Path) -> str | None:
        return committed_text

    notes = discover_notes(tmp_path)
    exp_note = next(n for n in notes if n.rel_path.endswith("EXP-0001-teste.md"))
    findings, checked = check_exp_rewrite(exp_note, fake_read_head)

    assert checked is True
    assert len(findings) == 1
    assert findings[0].categoria == "exp_reescrita"
    assert "2026-09-06" in findings[0].detalhe


def test_exp_rewrite_appended_section_is_not_reported(tmp_path: Path) -> None:
    _home(tmp_path)
    note_path = _exp_note(tmp_path, _COMMITTED_SECTIONS)
    committed_text = note_path.read_text(encoding="utf-8")

    appended_text = committed_text + "\n### Avaliação de 2026-09-08 — turno 2\nnovo conteúdo.\n"
    note_path.write_text(appended_text, encoding="utf-8")

    def fake_read_head(_abs_path: Path) -> str | None:
        return committed_text

    notes = discover_notes(tmp_path)
    exp_note = next(n for n in notes if n.rel_path.endswith("EXP-0001-teste.md"))
    findings, checked = check_exp_rewrite(exp_note, fake_read_head)

    assert checked is True
    assert findings == []


def test_exp_rewrite_placeholder_heading_without_date_is_exempt(tmp_path: Path) -> None:
    _home(tmp_path)
    note_path = _exp_note(tmp_path, _COMMITTED_SECTIONS)
    committed_text = note_path.read_text(encoding="utf-8")

    changed_text = committed_text.replace(
        "preencher quando houver nova leitura.", "TEXTO DIFERENTE NO PLACEHOLDER."
    )
    note_path.write_text(changed_text, encoding="utf-8")

    def fake_read_head(_abs_path: Path) -> str | None:
        return committed_text

    notes = discover_notes(tmp_path)
    exp_note = next(n for n in notes if n.rel_path.endswith("EXP-0001-teste.md"))
    findings, checked = check_exp_rewrite(exp_note, fake_read_head)

    assert checked is True
    assert findings == []


def test_exp_rewrite_skips_gracefully_when_no_git(tmp_path: Path) -> None:
    _home(tmp_path, "[[EXP-0001-teste]]")
    _exp_note(tmp_path, _COMMITTED_SECTIONS)

    report, exit_code = lint(tmp_path, "text", no_git=True)

    assert "exp_reescrita desativada" in report
    assert not _has_section(report, "Reescrita de experimentos (append-only)")
    assert exit_code == 0
    assert "RESULTADO: base limpa" in report


# -- resolução de alvos (T3.21: os três defeitos do linter) ---------------------


def test_partial_path_link_resolves_like_obsidian(tmp_path: Path) -> None:
    """``[[Dialogos/M3]]`` acha ``06-DECISIONS/Dialogos/M3.md``: o Obsidian casa
    qualquer sufixo de caminho em fronteira de barra, não só o caminho inteiro."""
    _home(tmp_path, "[[Dialogos/M3]]")
    _basic_note(tmp_path, "pasta/Dialogos/M3.md", "M3")

    report, exit_code = lint(tmp_path, "text", no_git=True)

    assert exit_code == 0, report
    assert "RESULTADO: base limpa" in report
    assert not _has_section(report, "Links mortos")
    assert not _has_section(report, "Notas órfãs")


def test_partial_path_link_matching_two_notes_is_ambiguous(tmp_path: Path) -> None:
    _home(tmp_path)
    _basic_note(tmp_path, "a/Dialogos/M3.md", "M3 a")
    _basic_note(tmp_path, "b/Dialogos/M3.md", "M3 b")
    _basic_note(tmp_path, "Nota A.md", "Nota A", body="[[Dialogos/M3]]\n")

    report, exit_code = lint(tmp_path, "text", no_git=True)

    assert exit_code == 1
    assert "Dialogos/M3" in _section(report, "Links ambíguos")
    assert not _has_section(report, "Links mortos")


def test_partial_path_only_matches_on_slash_boundary(tmp_path: Path) -> None:
    """``[[gos/M3]]`` não é sufixo de caminho de ``Dialogos/M3.md`` — é morto."""
    _home(tmp_path, "[[Dialogos/M3]]")
    _basic_note(tmp_path, "pasta/Dialogos/M3.md", "M3", body="[[gos/M3]]\n")

    report, exit_code = lint(tmp_path, "text", no_git=True)

    assert exit_code == 1
    assert "gos/M3" in _section(report, "Links mortos")


def test_base_and_canvas_files_are_link_targets(tmp_path: Path) -> None:
    """`.base`/`.canvas` entram no índice de alvos (e não viram nota nem órfã)."""
    _home(tmp_path, "[[Experimentos.base]] e [[Fluxo sinal → carteira.canvas]]")
    _write(tmp_path, "05-EXPERIMENTS/Experimentos.base", "views: []\n")
    _write(tmp_path, "01-ARCHITECTURE/Fluxo sinal → carteira.canvas", '{"nodes": []}\n')

    report, exit_code = lint(tmp_path, "text", no_git=True)

    assert exit_code == 0, report
    # Os dois arquivos são alvos, não notas: só 00-HOME.md entra na contagem.
    assert "1 NOTA(S) ANALISADA(S)" in report
    assert "RESULTADO: base limpa" in report


def test_link_to_base_file_without_extension_is_dead(tmp_path: Path) -> None:
    """O Obsidian só encontra um não-``.md`` pelo nome com extensão."""
    _home(tmp_path, "[[Experimentos]]")
    _write(tmp_path, "05-EXPERIMENTS/Experimentos.base", "views: []\n")

    report, exit_code = lint(tmp_path, "text", no_git=True)

    assert exit_code == 1
    assert "Experimentos" in _section(report, "Links mortos")


# -- exceções de pasta ---------------------------------------------------------


def test_template_note_may_leave_declared_keys_empty(tmp_path: Path) -> None:
    """Num ``_TEMPLATE-*`` a chave vazia é o próprio conteúdo: exige-se presença."""
    _home(tmp_path, "[[_TEMPLATE-NOTE]]")
    _write(
        tmp_path,
        "11-KNOWLEDGE/_TEMPLATE-NOTE.md",
        "---\ntags: [knowledge]\nstatus: template\nowner: sexta-feira\n"
        'updated: 2026-09-08\nfonte: \nlido_em: \nconfiança: "?"\n---\n# Título\n',
    )

    report, exit_code = lint(tmp_path, "text", no_git=True)

    assert exit_code == 0, report
    assert "RESULTADO: base limpa" in report


def test_template_note_missing_key_altogether_is_still_reported(tmp_path: Path) -> None:
    _home(tmp_path, "[[_TEMPLATE-NOTE]]")
    _write(
        tmp_path,
        "11-KNOWLEDGE/_TEMPLATE-NOTE.md",
        "---\ntags: [knowledge]\nstatus: template\nowner: sexta-feira\n"
        "updated: 2026-09-08\nfonte: \n---\n# Título\n",
    )

    report, exit_code = lint(tmp_path, "text", no_git=True)

    assert exit_code == 1
    section = _section(report, "Frontmatter incompleto")
    assert "lido_em" in section
    assert "confiança" in section


def test_estrategias_readme_is_not_asked_for_a_strategy_key(tmp_path: Path) -> None:
    """``03-TRADING/Estrategias/README.md`` é a convenção do catálogo (T3.20),
    não uma página de estratégia."""
    _home(tmp_path, "[[Estrategias/README]]")
    _write(
        tmp_path,
        "03-TRADING/Estrategias/README.md",
        "---\ntags: [estrategia, catalogo]\nupdated: 2026-09-08\n---\n# Convenção\n",
    )

    report, exit_code = lint(tmp_path, "text", no_git=True)

    assert exit_code == 0, report
    assert "RESULTADO: base limpa" in report
