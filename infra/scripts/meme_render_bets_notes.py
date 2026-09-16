"""T4.25 — the meme charts as pages of the vault: one per rule set, plus the diary.

Two writes, both **by appending**: ``03-TRADING/Meme/Apostas-tracadas/<conjunto>.md``
(one page per frozen rule set — pre-registration, ruler, and one ``## Dia
<AAAA-MM-DD>`` block per day with the gallery and the table; a day already on the
page is replaced by itself, another day is never rewritten) and the day's
``09-OPERATIONS/Diario-Meme/<dia>.md``, which gains a ``## 7. Gráficos`` section
after the archivist's section 6 and nothing else. Links are **markdown** embeds
with a relative path, the vault's own convention for images: ``.png`` is not a
linkable target for ``obsidian_lint.py`` (``ASSET_SUFFIXES`` is ``.base``/
``.canvas``), so a ``![[…png]]`` wikilink would be reported as a dead link.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

from meme_render_bets_model import Bet, rule_set_slug

REPO_ROOT = Path(__file__).resolve().parents[2]
VAULT = REPO_ROOT / "obsidian"
SETS_DIR = VAULT / "03-TRADING" / "Meme" / "Apostas-tracadas"
DIARY_DIR = VAULT / "09-OPERATIONS" / "Diario-Meme"
ATTACH = VAULT / "attachments" / "meme"
MEME_README = VAULT / "03-TRADING" / "Meme" / "README.md"
INDEX_LINK = "[[03-TRADING/Meme/Apostas-tracadas/README|Operações traçadas (meme)]]"
DIARY_HEADING = "## 7. Gráficos"

RULER_KEYS = (
    ("size_sol", "tamanho (SOL)"),
    ("target_x", "alvo (×)"),
    ("trailing_pct", "trailing (%)"),
    ("trailing_arm_x", "arma o trailing (×)"),
    ("max_hold_s", "tempo máximo (s)"),
    ("max_loss_pct", "piso de perda (%)"),
    ("exit_on_line_break", "sai na linha rompida"),
    ("exit_on_migration", "sai na migração"),
    ("clock", "relógio"),
)
"""The numbers a reader needs to judge a chart, in the order the exits fire."""


def attachments_dir(day: date, rule_set: str) -> Path:
    return ATTACH / day.isoformat() / rule_set_slug(rule_set)


def _rel(from_note: Path, target: Path) -> str:
    """Relative POSIX path, with the ``+`` of a positive R percent-encoded."""
    parts = Path(target).relative_to(VAULT).parts
    ups = "../" * (len(from_note.relative_to(VAULT).parts) - 1)
    return ups + "/".join(quote(part) for part in parts)


def exp_link(exp_ref: str | None) -> str:
    """Só entra ``[[wikilink]]`` de página que **existe** — link morto é achado do linter."""
    if not exp_ref:
        return "(conjunto `operator` — sem pré-registro; a mesa decide)"
    matches = sorted(p.stem for p in (VAULT / "05-EXPERIMENTS").glob(f"{exp_ref}-*.md"))
    return f"[[{matches[0]}]]" if matches else f"`{exp_ref}` (ainda sem página no vault)"


def _fmt(value: object) -> str:
    if isinstance(value, bool):
        return "sim" if value else "não"
    return "—" if value is None else f"`{value}`"


def ruler(bet: Bet) -> list[str]:
    params = bet.rule_set_params or bet.params
    rows = [f"| {label} | {_fmt(params.get(key))} |" for key, label in RULER_KEYS]
    return ["| régua congelada | valor |", "|---|---|", *rows]


def _table(bets: Sequence[Bet], note: Path) -> list[str]:
    head = [
        "| hora (BRT) | símbolo | mint | R | saída | gráfico |",
        "|---|---|---|---|---|---|",
    ]
    for bet in bets:
        png = attachments_dir(bet.day, bet.rule_set) / bet.filename()
        link = (
            f"[{bet.filename()}]({_rel(note, png)})"
            if png.exists()
            else "(gráfico não desenhado ainda)"
        )
        quality = "" if bet.measured else f" (indeterminada: {bet.outcome_quality_reason})"
        head.append(
            f"| {bet.entry_brt:%H:%M:%S} | {bet.ticker} | `{bet.mint[:10]}…` | {bet.r_text} "
            f"| {bet.exit_reason}{quality} | {link} |"
        )
    return head


def _embed(bet: Bet, note: Path) -> list[str]:
    """O embed do PNG — ou a frase honesta de que ele ainda não foi desenhado."""
    png = attachments_dir(bet.day, bet.rule_set) / bet.filename()
    if not png.exists():
        return ["(gráfico ainda não desenhado — rodar `meme_render_bets.py render`.)", ""]
    return [f"![{bet.ticker} {bet.rule_set} {bet.entry_brt:%d/%m %H:%M}]({_rel(note, png)})", ""]


def _line(bet: Bet) -> str:
    return (
        f"{bet.ticker} · {bet.entry_brt:%H:%M:%S} BRT · {bet.r_text} R · "
        f"saída por `{bet.exit_reason}`"
    )


def _gallery(bets: Sequence[Bet], note: Path) -> list[str]:
    """Melhor, pior e mais recente do dia; rótulos que caem na mesma aposta somam."""
    measured = [b for b in bets if b.measured] or list(bets)
    picks = (
        ("Melhor", max(measured, key=lambda b: b.r_multiple)),
        ("Pior", min(measured, key=lambda b: b.r_multiple)),
        ("Mais recente", max(bets, key=lambda b: b.entry_at)),
    )
    labels: dict[str, tuple[list[str], Bet]] = {}
    for label, bet in picks:
        labels.setdefault(bet.bet_id, ([], bet))[0].append(label)
    out: list[str] = []
    for names, bet in labels.values():
        out += [f"**{' · '.join(names)}** — {_line(bet)}.", "", *_embed(bet, note)]
    return out


def day_block(day: date, bets: Sequence[Bet], note: Path) -> str:
    measured = [b for b in bets if b.measured]
    total = sum((b.r_multiple for b in measured), Decimal(0))
    body = [
        f"## Dia {day.isoformat()}",
        "",
        f"{len(bets)} aposta(s) fechada(s) — {len(measured)} medida(s), "
        f"{len(bets) - len(measured)} indeterminada(s). Soma de R das medidas: "
        f"**{total:+.4f}**.",
        "",
        *_gallery(bets, note),
        *_table(bets, note),
        "",
    ]
    return "\n".join(body)


def _frontmatter(bet: Bet, day: date, previous: str | None) -> str:
    """``updated`` never walks backwards: redesenhar um dia velho não rejuvenesce a página."""
    updated = day.isoformat()
    match = re.search(r"^updated:\s*(\d{4}-\d{2}-\d{2})", previous or "", re.MULTILINE)
    if match and match.group(1) > updated:
        updated = match.group(1)
    keys = {
        "tags": "[operacoes, meme, pumpfun, graficos, m4]",
        "status": "em-andamento",
        "owner": "quant-engineer",
        "updated": updated,
        "rule_set": bet.rule_set,
        "kind": bet.kind,
        "exp": bet.exp_ref or "—",
        "code_ref": bet.code_ref or "—",
    }
    return "---\n" + "".join(f"{k}: {v}\n" for k, v in keys.items()) + "---\n"


def page_head(bet: Bet, day: date, previous: str | None) -> str:
    return "\n".join(
        [
            _frontmatter(bet, day, previous),
            f"# {bet.rule_set} — apostas traçadas",
            "",
            f"Uma imagem por aposta **fechada** do conjunto `{bet.rule_set}` "
            f"({bet.kind}), desenhada por `infra/scripts/meme_render_bets.py` a partir de "
            "`meme_paper_bets`, `meme_features_15s`, `meme_features_1m` e "
            "`meme_curve_snapshots` — nenhum número desta página foi digitado à mão.",
            "",
            f"**Pré-registro congelado:** {exp_link(bet.exp_ref)}. As linhas desenhadas são as "
            "**features** do fold (`support_line_sol`, `high_15m_sol`, `breakout_15m`, "
            "`higher_lows`, T4.10), lidas no minuto fechado da entrada — a mesma geometria da tela "
            "`/meme/{mint}` (`apps/web/components/meme/meme-lines.ts`). Para um conjunto que não lê "
            "linha para decidir elas são **contexto**, nunca entrada da decisão.",
            "",
            "**Faixas com `≈`:** alvo, piso, arme e trailing medem a **marca em SOL** (o que uma "
            "venda cheia renderia, taxas incluídas — `docs/RISK_ENGINE_MEME.md` §6), não a "
            "capitalização; no gráfico os múltiplos aparecem aplicados ao mcap da entrada. O R do "
            "título é o da linha da aposta.",
            "",
            *ruler(bet),
            "",
            "Reproduzir: `docs/PIPELINE.md` §9c. Diário do dia: "
            f"[[09-OPERATIONS/Diario-Meme/README|Diário Meme]]. Índice: {INDEX_LINK}.",
            "",
        ]
    )


def _split(text: str) -> tuple[str, list[tuple[str, str]]]:
    """``(head, [(heading, block)])`` splitting on top-level ``## `` headings."""
    lines = text.splitlines(keepends=True)
    head: list[str] = []
    sections: list[tuple[str, str]] = []
    current: str | None = None
    body: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if current is not None:
                sections.append((current, "".join(body)))
            current, body = line.rstrip("\n"), []
        elif current is None:
            head.append(line)
        else:
            body.append(line)
    if current is not None:
        sections.append((current, "".join(body)))
    return "".join(head), sections


def upsert_section(text: str, heading: str, block: str, *, sorted_by_heading: bool) -> str:
    """Replace the section with ``heading``, else insert it (sorted or appended)."""
    head, sections = _split(text)
    body = block.split("\n", 1)[1] if "\n" in block else ""
    entry = (heading, body if body.endswith("\n") else body + "\n")
    for index, (existing, _) in enumerate(sections):
        if existing == heading:
            sections[index] = entry
            break
    else:
        position = len(sections)
        if sorted_by_heading:
            position = next((i for i, (h, _) in enumerate(sections) if h > heading), len(sections))
        sections.insert(position, entry)
    # Uma linha em branco antes **do nosso** cabeçalho, e só dele: a seção 6 do
    # diário é do arquivista e não se toca nem no espaço em branco dela.
    out = head
    for existing, chunk in sections:
        if existing == heading and out and not out.endswith("\n\n"):
            out += "\n"
        out += f"{existing}\n{chunk}"
    return out


def write_set_page(day: date, rule_set: str, bets: Sequence[Bet]) -> Path:
    """Cabeçalho regenerado (é derivado), blocos de dia preservados palavra por palavra."""
    path = SETS_DIR / f"{rule_set_slug(rule_set)}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    previous = path.read_text(encoding="utf-8") if path.exists() else None
    text = page_head(bets[0], day, previous)
    if previous is not None:
        text += "".join(f"{h}\n{b}" for h, b in _split(previous)[1])
    day_heading = f"## Dia {day.isoformat()}"
    text = upsert_section(text, day_heading, day_block(day, bets, path), sorted_by_heading=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_index(day: date) -> Path:
    path = SETS_DIR / "README.md"
    pages = sorted(p.stem for p in SETS_DIR.glob("*.md") if p.stem != "README")
    body = [
        "---\ntags: [operacoes, meme, pumpfun, graficos, m4]\nstatus: em-andamento\n"
        f"owner: quant-engineer\nupdated: {day.isoformat()}\n---",
        "",
        "# Operações traçadas (meme) — índice",
        "",
        "Uma página por conjunto de regras, um gráfico por aposta **fechada** (entrou, saiu, R "
        "apurado na linha de `meme_paper_bets`). Gerado por `meme_render_bets.py notes` — "
        "`docs/PIPELINE.md` §9c.",
        "",
        *[f"- [[03-TRADING/Meme/Apostas-tracadas/{name}]]" for name in pages],
        "",
        "As linhas destes gráficos são **features** calculadas pelo fold (`meme_features_v3`, "
        "`docs/DATABASE.md` §38.1), não desenho à mão: suporte pelos dois últimos fundos locais, "
        "máxima da janela anterior de 15 min, rompimento. Quem **lê** linha para decidir é o "
        "conjunto cujo portão a exige ([[EXP-M2-a-linha-manda]]); nos demais a linha é contexto.",
        "",
        "Irmã de [[03-TRADING/Operacoes-tracadas/README|Operações traçadas (perps/spot)]] e de "
        "[[03-TRADING/Meme/README|Meme (Trading)]].",
        "",
    ]
    path.write_text("\n".join(body), encoding="utf-8")
    return path


def link_index_from_meme_readme() -> bool:
    """One inbound link so the index is not an orphan for ``obsidian_lint.py``."""
    if not MEME_README.exists():
        return False
    text = MEME_README.read_text(encoding="utf-8")
    if INDEX_LINK in text:
        return False
    block = (
        "\n## Operações traçadas\n\nUm gráfico por aposta fechada, uma página por conjunto: "
        f"{INDEX_LINK} — desenhadas por `meme_render_bets.py` (`docs/PIPELINE.md` §9c).\n"
    )
    MEME_README.write_text(text.rstrip("\n") + "\n" + block, encoding="utf-8")
    return True


def diary_block(day: date, bets: Sequence[Bet], note: Path) -> str:
    lines = [
        DIARY_HEADING,
        "",
        f"Gerado por `infra/scripts/meme_render_bets.py notes` — {len(bets)} aposta(s) fechada(s) "
        "do dia, uma imagem cada (mcap teórico em SOL, linhas do fold, entrada, saída, venda do "
        f"criador). Páginas por conjunto: {INDEX_LINK}.",
        "",
    ]
    for rule_set in sorted({b.rule_set for b in bets}):
        mine = [b for b in bets if b.rule_set == rule_set]
        slug = rule_set_slug(rule_set)
        lines += [
            f"### `{rule_set}` — {len(mine)} aposta(s) "
            f"[[03-TRADING/Meme/Apostas-tracadas/{slug}|(página do conjunto)]]",
            "",
        ]
        for bet in mine:
            lines += [*_embed(bet, note), f"{_line(bet)}.", ""]
    return "\n".join(lines)


def write_diary_section(day: date, bets: Sequence[Bet]) -> Path | None:
    path = DIARY_DIR / f"{day.isoformat()}.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    updated = upsert_section(
        text, DIARY_HEADING, diary_block(day, bets, path), sorted_by_heading=False
    )
    if updated != text:
        path.write_text(updated, encoding="utf-8")
    return path


def write_notes(bets: Iterable[Bet]) -> list[Path]:
    """Every page one JSONL touches, in the order they are written."""
    rows = sorted(bets, key=lambda b: (b.rule_set, b.entry_at))
    if not rows:
        return []
    day = rows[0].day
    written: list[Path] = []
    for rule_set in sorted({b.rule_set for b in rows}):
        written.append(write_set_page(day, rule_set, [b for b in rows if b.rule_set == rule_set]))
    written.append(write_index(day))
    if link_index_from_meme_readme():
        written.append(MEME_README)
    diary = write_diary_section(day, rows)
    if diary is not None:
        written.append(diary)
    return written
