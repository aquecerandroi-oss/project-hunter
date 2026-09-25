#!/usr/bin/env python3
"""The automatic daily ficha (T4.92) — Everton's ask: every real trade gets a
sheet with its metrics and motives, from the database, without depending on
anyone remembering, so losses are classified and the biggest leak shows up by
itself.

    uv run python infra/scripts/meme_daily_ficha.py                    # yesterday (Brasília), stdout
    uv run python infra/scripts/meme_daily_ficha.py --day 2026-09-24
    uv run python infra/scripts/meme_daily_ficha.py --week              # last 7 days by loss class

On the VPS it runs inside the published image, like every other ops tool::

    bash infra/vps/compose.sh ops python infra/scripts/meme_daily_ficha.py --day 2026-09-24

Reads only, as ``hunter_app`` (``SELECT`` on ``meme_live_*``, ``meme_proposals``,
``meme_rule_sets``, ``meme_decision_tapes``, ``meme_trades``, ``meme_tokens``,
``meme_features_1m``, ``meme_paper_bets``, ``spot_positions``). Prints Markdown
to stdout; writing the note into the vault is ``meme_daily_ficha.sh``'s job
(it runs this over SSH and writes the output locally — this script itself
never touches a file).
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from meme_daily_ficha_queries import SAO_PAULO, gather_day, gather_week
from meme_daily_ficha_render import Ficha, render_day, render_week

from hunter_core.domain.types import utcnow

__all__ = ["default_day", "git_sha", "main"]

REPO_ROOT = Path(__file__).resolve().parents[2]


def default_day(now: datetime | None = None) -> date:
    """Yesterday, in Brasília — the day that just closed."""
    at = utcnow() if now is None else now
    return at.astimezone(SAO_PAULO).date() - timedelta(days=1)


def git_sha() -> str:
    """The short SHA that produced this run — ``HUNTER_RELEASE`` first (baked
    into the deployed image at build time, ``infra/docker/Dockerfile.api-workers``
    ``ARG GIT_SHA`` -> ``ENV HUNTER_RELEASE``; the VPS's ``ops`` container has
    no ``.git`` to ask), then ``git rev-parse`` for a local dev checkout,
    ``desconhecido`` when neither answers — never blocks the ficha: the
    frontmatter just says so instead."""
    release = os.environ.get("HUNTER_RELEASE", "").strip()
    if release and release != "unknown":
        return release
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return result.stdout.strip() or "desconhecido"
    except (OSError, subprocess.SubprocessError):
        return "desconhecido"


async def _run(args: argparse.Namespace) -> int:
    sha = git_sha()
    if args.week:
        end_day = date.fromisoformat(args.day) if args.day else default_day()
        by_day = await gather_week(end_day)
        print(render_week(by_day, generated_at=utcnow(), git_sha=sha))
        return 0
    day = date.fromisoformat(args.day) if args.day else default_day()
    data = await gather_day(day)
    ficha = Ficha(data=data, generated_at=utcnow(), git_sha=sha)
    print(render_day(ficha))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--day",
        help="dia em Brasília, AAAA-MM-DD (padrão: ontem; com --week, o fim da janela de 7 dias)",
    )
    parser.add_argument(
        "--week", action="store_true", help="resumo dos últimos 7 dias por classe de perda"
    )
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[reportUnknownMemberType]
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
