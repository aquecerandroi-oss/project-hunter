#!/usr/bin/env python3
"""Register a "may pump" event — audited, dry-run by default (T4.26).

    uv run python infra/scripts/meme_event.py add \\
        --kind public_figure_launch --title "X anuncia moeda no perfil oficial" \\
        --url "https://x.com/handle/status/123" --handle handle \\
        --confidence confirmed --recorded-by sexta-feira                        # dry-run
    uv run python infra/scripts/meme_event.py add \\
        --kind public_figure_launch --title "X anuncia moeda no perfil oficial" \\
        --handle handle --confidence confirmed --recorded-by sexta-feira --apply

``add`` inserts one ``meme_events`` row — ``mint`` is almost always unset at
this point (the per-minute matching job, ``hunter_meme_worker.events``, fills
it later); a human may pass ``--mint`` directly when the coin already exists.
Every applied run leaves a ``system_events`` row with the title, the same
audit ``meme_rule_set.py`` leaves.

Refusals, by name and with nothing written: ``kind_unknown``,
``confidence_unknown``, ``action_unknown``, ``recorded_by_required``.

``rematch --hours 72 [--apply]`` (T4.26b) re-runs the per-minute job's own
rule by hand over ``observed_at >= now - hours``, so an event registered
under the pre-T4.26b 65-minute lookback gets its coins without waiting for
its own age to fall inside a fresh window (see
``hunter_meme_worker.events_repo`` for the live loop).

Connects with ``DATABASE_URL_MIGRATIONS`` (direct, never the pooler).
Exit codes: 0 done, 64 usage, 65 refused.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from meme_event_rematch import rematch
from meme_ops_db import migration_url, record_event
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

COMPONENT = "meme_event"
EVENT_SOURCES = ("plantao", "baha", "indexer_boost", "dexscreener_profile", "manual")
EVENT_KINDS = (
    "public_figure_launch",
    "exchange_listing",
    "viral_post",
    "brand_launch",
    "narrative",
    "incident",
)
EVENT_CONFIDENCES = ("confirmed", "reported", "rumor")
MATCH_ACTIONS = ("buy", "avoid")
"""T4.26b: ``notes->>'action'`` — ``avoid`` marks every coin the matching job
names as a warning, never a buy signal (the event gate's ``event_avoid``)."""
EX_USAGE, EX_REFUSED = 64, 65

__all__ = ["Refused", "insert_event", "main", "run"]


class Connection(Protocol):
    async def execute(self, statement: Any, parameters: Any = None, /) -> Any: ...


class Refused(Exception):
    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason


_INSERT = text(
    "INSERT INTO meme_events (id, observed_at, source, kind, title, url, mint, "
    "  symbol_hint, handle_hint, confidence, notes, recorded_by) "
    "VALUES (gen_random_uuid(), :observed_at, :source, :kind, :title, :url, :mint, "
    "  :symbol_hint, :handle_hint, :confidence, CAST(:notes AS jsonb), :recorded_by) "
    "RETURNING id::text"
)


def _strip_handle(handle: str | None) -> str | None:
    return None if handle is None else handle.lstrip("@").strip() or None


def _csv(raw: str | None) -> list[str]:
    return [] if raw is None else [item.strip() for item in raw.split(",") if item.strip()]


def _build_notes(
    *, notes: str | None, tickers: str | None, keywords: str | None, action: str | None
) -> dict[str, Any]:
    """T4.26b: ``--tickers``/``--keywords``/``--action`` are convenience over
    ``--notes`` (still accepted, still a raw JSON object) — the matching job
    reads ``notes->'tickers'``/``notes->'keywords'``/``notes->>'action'``
    directly, and a hand-written ``--notes`` JSON keeps working exactly as it
    did before this revision."""
    merged: dict[str, Any] = json.loads(notes) if notes else {}
    if tickers is not None:
        merged["tickers"] = _csv(tickers)
    if keywords is not None:
        merged["keywords"] = _csv(keywords)
    if action is not None:
        merged["action"] = action
    return merged


async def insert_event(conn: Connection, **fields: Any) -> str:
    (event_id,) = (await conn.execute(_INSERT, fields)).scalars().all()
    return str(event_id)


def _plan(fields: dict[str, Any]) -> str:
    return (
        f"add {fields['kind']} ({fields['confidence']}): {fields['title']!r}"
        f"\n  url={fields['url']} mint={fields['mint']} handle={fields['handle_hint']} "
        f"symbol={fields['symbol_hint']}\n  observed_at={fields['observed_at'].isoformat()} "
        f"recorded_by={fields['recorded_by']}"
    )


async def run(
    conn: Connection,
    *,
    kind: str,
    title: str,
    url: str | None,
    mint: str | None,
    handle: str | None,
    symbol: str | None,
    confidence: str,
    source: str,
    observed_at: datetime | None,
    notes: str | None,
    recorded_by: str | None,
    apply: bool,
    tickers: str | None = None,
    keywords: str | None = None,
    action: str | None = None,
) -> tuple[int, str]:
    """``(exit code, report)``. Writes only with ``add --apply``."""
    if kind not in EVENT_KINDS:
        raise Refused("kind_unknown", f"{kind!r}; one of {EVENT_KINDS}")
    if confidence not in EVENT_CONFIDENCES:
        raise Refused("confidence_unknown", f"{confidence!r}; one of {EVENT_CONFIDENCES}")
    if source not in EVENT_SOURCES:
        raise Refused("source_unknown", f"{source!r}; one of {EVENT_SOURCES}")
    if action is not None and action not in MATCH_ACTIONS:
        raise Refused("action_unknown", f"{action!r}; one of {MATCH_ACTIONS}")
    if recorded_by is None or not recorded_by.strip():
        raise Refused("recorded_by_required", "--recorded-by names who is registering this")
    fields: dict[str, Any] = {
        "kind": kind,
        "title": title,
        "url": url,
        "mint": mint,
        "handle_hint": _strip_handle(handle),
        "symbol_hint": symbol,
        "confidence": confidence,
        "source": source,
        "observed_at": observed_at or datetime.now(UTC),
        "notes": json.dumps(
            _build_notes(notes=notes, tickers=tickers, keywords=keywords, action=action)
        ),
        "recorded_by": recorded_by.strip(),
    }
    plan = _plan(fields)
    if not apply:
        return 0, plan + "\ndry-run: nothing written (add --apply)"
    event_id = await insert_event(conn, **fields)
    await record_event(
        conn,
        component=COMPONENT,
        level="info",
        event="added",
        message=f"{event_id}: {kind} ({confidence}) {title!r} by {fields['recorded_by']}",
    )
    return 0, plan + f"\napplied: meme_events {event_id}; system_events written"


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])  # type: ignore[union-attr]
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add", help="register one may-pump event")
    add.add_argument("--kind", required=True, choices=EVENT_KINDS)
    add.add_argument("--title", required=True)
    add.add_argument("--url", default=None)
    add.add_argument("--mint", default=None)
    add.add_argument("--handle", default=None, help="the announcer's @handle, with or without @")
    add.add_argument("--symbol", default=None)
    add.add_argument("--confidence", required=True, choices=EVENT_CONFIDENCES)
    add.add_argument("--source", default="manual", choices=EVENT_SOURCES)
    add.add_argument("--observed-at", default=None, help="ISO 8601, default now")
    add.add_argument("--notes", default=None, help="a JSON object")
    add.add_argument(
        "--tickers", default=None, help="comma-separated, merged into notes.tickers (T4.26b)"
    )
    add.add_argument(
        "--keywords", default=None, help="comma-separated, merged into notes.keywords (T4.26b)"
    )
    add.add_argument(
        "--action",
        default=None,
        choices=MATCH_ACTIONS,
        help="merged into notes.action; 'avoid' refuses every matched coin (T4.26b)",
    )
    add.add_argument("--recorded-by", required=True)
    add.add_argument("--apply", action="store_true")

    rematch_parser = sub.add_parser(
        "rematch", help="backfill: match every event against meme_tokens (T4.26b)"
    )
    rematch_parser.add_argument(
        "--hours", type=int, default=72, help="observed_at lookback window, default 72"
    )
    rematch_parser.add_argument("--apply", action="store_true")
    return parser.parse_args(argv)


async def _run_add(conn: Connection, args: argparse.Namespace) -> tuple[int, str]:
    observed_at = None if args.observed_at is None else datetime.fromisoformat(args.observed_at)
    return await run(
        conn,
        kind=args.kind,
        title=args.title,
        url=args.url,
        mint=args.mint,
        handle=args.handle,
        symbol=args.symbol,
        confidence=args.confidence,
        source=args.source,
        observed_at=observed_at,
        notes=args.notes,
        tickers=args.tickers,
        keywords=args.keywords,
        action=args.action,
        recorded_by=args.recorded_by,
        apply=args.apply,
    )


async def _main(argv: Sequence[str]) -> int:
    args = _parse(argv)
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as conn, conn.begin():
            try:
                if args.command == "add":
                    code, report = await _run_add(conn, args)
                else:
                    code, report = await rematch(
                        conn, hours=args.hours, now=datetime.now(UTC), apply=args.apply
                    )
            except Refused as refused:
                print(f"refused: {refused}", file=sys.stderr)
                return EX_REFUSED
        print(report)
        return code
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_main(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
