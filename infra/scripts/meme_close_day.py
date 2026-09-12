"""Close one Brasília day of the meme Lab — the lessons written by the rows.

T4.15 (Everton, 12/09/2026: "ele vai se auto aprimorando a cada leitura, a
cada compra e venda")::

    uv run python infra/scripts/meme_close_day.py --dry-run                  # ontem (Brasília), stdout
    uv run python infra/scripts/meme_close_day.py --day 2026-09-12 --dry-run
    uv run python infra/scripts/meme_close_day.py --day 2026-09-12 --apply

On the VPS it runs inside the published image, by cron at 00:10 BRT
(``docs/DEPLOYMENT.md`` §3.6b)::

    bash infra/vps/compose.sh ops python infra/scripts/meme_close_day.py --apply

Reads only, as ``hunter_app``; ``--apply`` writes, in this order and each one
append-only: (1) ``obsidian/09-OPERATIONS/Diario-Meme/<dia>.md`` — the diary of
``meme_diary.py`` with section 6 filled by the lessons (a note that already has
a written section 6 is **refused**; one whose section 6 is still the
archivist's stub is completed); (2) a dated evaluation on every active EXP-M*
page that closed a bet in the day; (3) ``M-L`` rows in
``obsidian/00-INBOX/Hipoteses-do-plantao.md`` — only for the lessons whose
contrast passed the ruler; (4) the diary folder's index line; (5)
``.claude/state/lote-meme-<dia+1>.md`` — the next batch, **as a proposal**.
The default day is the one that just closed (yesterday in Brasília).
"""

from __future__ import annotations

import argparse
import asyncio
import io
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from meme_close_outputs import (
    INBOX_MARKER,
    append_evaluation,
    diary_index_line,
    exp_evaluation,
    frozen_prediction,
    inbox_rows,
    next_inbox_number,
    render_lote,
)
from meme_close_queries import gather_close
from meme_close_render import DIARY_STUB, CloseInputs, fill_section_six, render_lessons_section
from meme_diary import gather as gather_diary
from meme_diary_render import SAO_PAULO, render_diary

from hunter_core.domain.types import utcnow

__all__ = ["DIARY_STUB", "Targets", "apply_close", "default_day", "main"]

REPO_ROOT = Path(__file__).resolve().parents[2]
_EXP_PAGE = re.compile(r"^(EXP-M\d+)-.*\.md$")


@dataclass(frozen=True, slots=True)
class Targets:
    vault_root: Path
    state_dir: Path

    @property
    def diary_dir(self) -> Path:
        return self.vault_root / "09-OPERATIONS" / "Diario-Meme"

    @property
    def inbox(self) -> Path:
        return self.vault_root / "00-INBOX" / "Hipoteses-do-plantao.md"

    @property
    def experiments(self) -> Path:
        return self.vault_root / "05-EXPERIMENTS"


def default_day(now: datetime) -> date:
    """The Brasília day that just closed."""
    return now.astimezone(SAO_PAULO).date() - timedelta(days=1)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _rel(path: Path, targets: Targets) -> str:
    for root in (REPO_ROOT, targets.vault_root.parent, targets.state_dir.parent):
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            continue
    return str(path)


def exp_pages(targets: Targets) -> dict[str, Path]:
    """``exp_ref -> page`` for every ``EXP-M<n>-*.md`` in the vault."""
    pages: dict[str, Path] = {}
    if targets.experiments.is_dir():
        for path in sorted(targets.experiments.glob("EXP-M*.md")):
            match = _EXP_PAGE.match(path.name)
            if match:
                pages[match.group(1)] = path
    return pages


def read_predictions(targets: Targets) -> dict[str, str | None]:
    return {exp_ref: frozen_prediction(_read(path)) for exp_ref, path in exp_pages(targets).items()}


def _apply_diary(note: str, body: str, targets: Targets, day: date) -> str:
    target = targets.diary_dir / f"{day.isoformat()}.md"
    if target.exists():
        filled = fill_section_six(_read(target), body)
        if filled is None:
            print(
                f"RECUSADO: {_rel(target, targets)} já tem a seção 6 escrita (registro datado não se "
                "reescreve)",
                file=sys.stderr,
            )
            raise SystemExit(2)
        _write(target, filled)
        return f"diário: seção 6 completada em {_rel(target, targets)}"
    filled = fill_section_six(note, body)
    if filled is None:
        print("RECUSADO: a nota gerada não traz o stub da seção 6", file=sys.stderr)
        raise SystemExit(2)
    _write(target, filled)
    return f"diário: gravado {_rel(target, targets)}"


def _apply_experiments(
    inputs: CloseInputs, targets: Targets, predictions: Mapping[str, str | None]
) -> list[str]:
    pages = exp_pages(targets)
    actions: list[str] = []
    for exp in inputs.all_time:
        if not exp.exp_ref or exp.today_n == 0:
            continue
        page = pages.get(exp.exp_ref)
        if page is None:
            actions.append(
                f"{exp.exp_ref}: página não encontrada em {_rel(targets.experiments, targets)}"
            )
            continue
        block = exp_evaluation(inputs, exp, predictions.get(exp.exp_ref))
        appended = append_evaluation(_read(page), block)
        if appended is None:
            actions.append(
                f"{exp.exp_ref}: avaliação de {inputs.day.isoformat()} já existe (mantida)"
            )
            continue
        _write(page, appended)
        actions.append(f"{exp.exp_ref}: avaliação de {inputs.day.isoformat()} acrescentada")
    return actions


def _apply_inbox(inputs: CloseInputs, targets: Targets) -> str:
    text = _read(targets.inbox)
    marker = INBOX_MARKER.format(day=inputs.day.isoformat())
    if marker in text:
        return "INBOX: linhas do dia já existem (mantidas)"
    rows = inbox_rows(inputs, first_number=next_inbox_number(text))
    if not rows:
        return "INBOX: nenhuma lição passou a régua (nada acrescentado)"
    lines = text.splitlines(keepends=True)
    last = max(i for i, line in enumerate(lines) if line.startswith("|"))
    if not lines[last].endswith("\n"):
        lines[last] += "\n"
    lines[last + 1 : last + 1] = [row + "\n" for row in rows]
    _write(targets.inbox, "".join(lines))
    return f"INBOX: {len(rows)} linha(s) M-L acrescentada(s)"


def _apply_index(inputs: CloseInputs, targets: Targets) -> str:
    readme = targets.diary_dir / "README.md"
    text = _read(readme) if readme.exists() else ""
    if f"[[09-OPERATIONS/Diario-Meme/{inputs.day.isoformat()}|" in text:
        return f"README: índice já tem {inputs.day.isoformat()} (mantido)"
    body = text if text.endswith("\n") or not text else text + "\n"
    if "## Diários gerados" not in body:
        body += "\n## Diários gerados\n\n"
    _write(readme, body + diary_index_line(inputs) + "\n")
    return f"README: índice ganhou {inputs.day.isoformat()}"


def _apply_lote(inputs: CloseInputs, targets: Targets) -> str:
    target = targets.state_dir / f"lote-meme-{(inputs.day + timedelta(days=1)).isoformat()}.md"
    if target.exists():
        return f"lote: {_rel(target, targets)} já existe, mantido"
    _write(target, render_lote(inputs))
    return f"lote: gravado {_rel(target, targets)}"


def apply_close(
    note: str, inputs: CloseInputs, targets: Targets, *, predictions: Mapping[str, str | None]
) -> list[str]:
    """The five writes, in order; the diary refusal happens before any of them."""
    body = render_lessons_section(inputs)
    actions = [_apply_diary(note, body, targets, inputs.day)]
    actions += _apply_experiments(inputs, targets, predictions)
    actions.append(_apply_inbox(inputs, targets))
    actions.append(_apply_index(inputs, targets))
    actions.append(_apply_lote(inputs, targets))
    return actions


def _dry_run(
    note: str, inputs: CloseInputs, targets: Targets, predictions: Mapping[str, str | None]
) -> None:
    body = render_lessons_section(inputs)
    print(fill_section_six(note, body) or note)
    print("--- linhas M-L propostas para 00-INBOX/Hipoteses-do-plantao.md:")
    rows = inbox_rows(inputs, first_number=next_inbox_number(_read(targets.inbox)))
    print("\n".join(rows) if rows else "(nenhuma lição passou a régua)")
    for exp in inputs.all_time:
        if exp.exp_ref and exp.today_n:
            print(f"--- avaliação a acrescentar em {exp.exp_ref}:")
            print(exp_evaluation(inputs, exp, predictions.get(exp.exp_ref)))
    print("--- lote:")
    print(render_lote(inputs))
    print(
        f"--- dry-run: nada escrito; --apply gravaria o diário, as avaliações, as linhas M-L, o índice "
        f"e .claude/state/lote-meme-{(inputs.day + timedelta(days=1)).isoformat()}.md"
    )


async def _run(args: argparse.Namespace) -> int:
    day = date.fromisoformat(args.day) if args.day else default_day(utcnow())
    targets = Targets(vault_root=Path(args.vault_root), state_dir=Path(args.state_dir))
    predictions = read_predictions(targets)
    diary = await gather_diary(day)
    inputs = await gather_close(day, real_observed=diary.real_observed, predictions=predictions)
    note = render_diary(diary)
    print(f"fechamento do dia {day.isoformat()} (Brasília)")
    if not args.apply:
        _dry_run(note, inputs, targets, predictions)
        return 0
    if not inputs.bets and not args.allow_empty:
        print(
            "RECUSADO: nenhuma aposta fechada no dia; use --allow-empty para fechar mesmo assim",
            file=sys.stderr,
        )
        return 3
    for action in apply_close(note, inputs, targets, predictions=predictions):
        print(action)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--day", help="dia em Brasília, AAAA-MM-DD (padrão: ontem — o dia que fechou)"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="imprima tudo, não grave")
    mode.add_argument(
        "--apply", action="store_true", help="grave (append-only, idempotente por dia)"
    )
    parser.add_argument(
        "--allow-empty", action="store_true", help="feche um dia sem aposta fechada"
    )
    parser.add_argument("--vault-root", default=str(REPO_ROOT / "obsidian"), help="raiz do vault")
    parser.add_argument(
        "--state-dir", default=str(REPO_ROOT / ".claude" / "state"), help="onde vai o lote"
    )
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[reportUnknownMemberType]
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
