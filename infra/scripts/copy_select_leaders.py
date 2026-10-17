"""Freeze the leader list of the paper copy-trade pilot (decision 2026-10-09).

Reads the public pump.fun leaderboard anonymously (6 views, <= 30 requests per
run, stop on 401/403/429), applies the pre-declared rule in
``copy_leaders_rule.py`` (printed below with its sha256 on every run), reads
the follower count of each chosen wallet, and writes
``.claude/state/copy-pilot/leaders-<UTC>.json``: write-once, with ``known_at``,
the rule text and hash, the per-response times, every wallet's numbers and the
sha256 of the list. ``--include <address>`` (repeatable, up to 4) adds Everton's
own picks as stratum ``escolha_everton``; rule item 10 does not fix an order, so the
includes are sorted canonically (the same set freezes the same ``list_sha256`` and is
read in the same order).

The write-once check looks at ``leaders-*.json`` in ``--out-dir`` (default
``.claude/state/copy-pilot/``): pointing ``--out-dir`` elsewhere changes where it looks, so
a list in the default directory does not stop a run aimed at another one. ``--new-cohort
"<reason>"`` only has an effect when a predecessor exists there (it then links to it and
requires it to read back with a matching ``list_sha256``); with none it is ignored.
There is no cross-process lock: run ONE instance at a time (two concurrent runs could both
find the directory empty and each publish a cohort). ``--dry-run`` skips the write-once check
and writes nothing. The file is published
atomically (temp file, fsync, hard link that cannot overwrite).

It writes nothing to the database: the paper rule set is seeded later by a
reviewed migration. The board is not point-in-time (KB-0185): the list says
whom to watch from ``known_at`` on, never what they "would have made".

    uv run python infra/scripts/copy_select_leaders.py --dry-run
    uv run python infra/scripts/copy_select_leaders.py --include <address>
    uv run python infra/scripts/copy_select_leaders.py --new-cohort "<reason>"

Exit codes: 0 frozen; 2 a board could not be read (nothing written); 3 frozen
but some followers were not read (a stop or the budget); 4 a list already
exists (use ``--new-cohort``); 5 empty selection (nothing written);
64 bad ``--include``.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import copy_leaders_doc as doc
import copy_leaders_http as http
import copy_leaders_rule as rule
import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_DIR = REPO_ROOT / ".claude" / "state" / "copy-pilot"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freeze the paper copy-trade pilot's leader list.")
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        metavar="ADDRESS",
        help="Everton's pick (repeatable, max 4)",
    )
    parser.add_argument("--dry-run", action="store_true", help="read and print; write nothing")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--new-cohort",
        metavar="REASON",
        help="write a new cohort next to the existing one, linked to it",
    )
    return parser


def _say(text: str = "") -> None:
    print(text)


def main(
    argv: Sequence[str] | None = None,
    *,
    client: httpx.Client | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] | None = None,
) -> int:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")
    args = _parser().parse_args(argv)
    try:
        includes = rule.validate_includes(args.include)
    except rule.RuleError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 64

    _say(rule.RULE_TEXT)
    _say(f"\nsha256 da regra: {rule.RULE_SHA256}")

    previous = doc.existing_lists(args.out_dir)
    supersedes = None
    if previous and not args.dry_run:
        if not args.new_cohort:
            print(
                f"ERRO: já existe a lista {previous[-1].name}. A coorte é congelada; "
                "outra seleção só com --new-cohort '<motivo>' (a anterior fica intacta).",
                file=sys.stderr,
            )
            return 4
        try:
            supersedes = doc.supersedes_of(previous[-1], args.new_cohort)
        except doc.PredecessorError as exc:
            print(f"ERRO: {exc}", file=sys.stderr)
            return 4

    owns_client = client is None
    client = client or httpx.Client(
        base_url=http.BASE_URL, timeout=httpx.Timeout(20.0), follow_redirects=False
    )
    reader = http.PumpReader(client, now=now, sleep=sleep or time.sleep)
    try:
        try:
            boards = http.fetch_boards(reader)
        except http.BoardsIncomplete as exc:
            print(f"ERRO: quadro obrigatório incompleto, nenhuma seleção: {exc}", file=sys.stderr)
            return 2
        selection = rule.select(boards, includes)
        if not selection.leaders:
            print(
                "AVISO: nenhuma carteira passou na regra e não há --include: nada a congelar.",
                file=sys.stderr,
            )
            return 5
        followers = http.fetch_followers(reader, [leader.address for leader in selection.leaders])
    finally:
        if owns_client:
            client.close()

    known_at = doc.ceil_ms(now())
    document = doc.build_document(
        known_at=known_at,
        selection=selection,
        followers=followers,
        responses=reader.records,
        requests_used=reader.used,
        stop_reason=reader.stop_reason,
        supersedes=supersedes,
    )
    _say(f"\nrequisições: {reader.used}/{http.REQUEST_BUDGET}")
    for item in (r for r in document["responses"] if r["endpoint"] == "/pnl-leaderboard"):
        _say(
            f"  {item['params']['period']}:{item['params']['sort']}  HTTP {item['status']}  linhas={item['rows']} "
            f"malformadas={item['malformed_rows']}  janela_inicio_s={item['window_start_sec']}  recebido={item['received_at']}"
        )
    _say(f"funil: {document['funnel']}")
    _say("\n" + doc.render_table(document))
    _say(f"\nlist_sha256: {document['list_sha256']}\nknown_at: {document['known_at']}")

    if args.dry_run:
        _say("\nDRY-RUN: nada foi gravado.")
    else:
        try:
            path = doc.write_frozen(args.out_dir, document)
        except FileExistsError as exc:
            print(f"ERRO: a lista já existe, nada foi sobrescrito: {exc.filename}", file=sys.stderr)
            return 4
        _say(f"\nCONGELADA: {path}")

    if reader.stop_reason is not None:
        unread = [w for w in document["wallets"] if w["followers"]["count"] is None]
        print(
            f"AVISO: parada em {reader.stop_reason}: seguidores desconhecidos em "
            f"{len(unread)} carteira(s); a lista segue válida (seguidor é descritivo).",
            file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
