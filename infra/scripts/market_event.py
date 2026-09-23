#!/usr/bin/env python3
"""Register one headline about a (non-meme) market — audited, dry-run by default.

T4.82, design ``docs/design/tela-confluencia-mercado.md`` §8. Today the shift
reads baha.com and writes in the vault, so none of it reaches the database and
therefore none of it reaches the confluence screen. This is the cheapest
audited path from one to the other: no scraper, no write surface on the web
(the screen stays a pure read, §6), and ``recorded_by`` plus the two instants
explicit from the very first row.

    uv run python infra/scripts/market_event.py add \\
        --symbol ZECUSDT --source baha --kind listing \\
        --title "Binance lista ZEC em novos pares" \\
        --url "https://www.binance.com/en/support/announcement/123" \\
        --published-at 2026-09-23T14:32Z --confidence reported --by everton   # dry-run
    ... --apply                                                               # writes

``--published-at`` is **optional and never invented**: a source that does not
say when it published leaves the column ``NULL``, and the screen lists the item
with "horário de publicação desconhecido" instead of drawing a line at a time
nobody published (§3, overlay 4). ``--observed-at`` defaults to now — when
*we* saw it — and the two are kept apart because that is what lets the screen
separate "o que se sabia às 11:45" from "o que descobrimos depois" (§4C).

``--exchange`` is optional too: a venue notice names its venue, a macro
headline names none and must reach this symbol's screen on every venue.

Idempotent on ``(source, url)`` through the partial unique of
``0059_market_events``: re-running the same link writes one row, not two, and
says so. Every applied run that actually inserts leaves a ``system_events``
row (component ``market_events``), the same audit ``meme_event.py`` leaves.

Refusals, by name and with nothing written: ``symbol_required``,
``title_required``, ``kind_unknown``, ``confidence_unknown``,
``source_unknown``, ``recorded_by_required``, ``naive_datetime``,
``observed_before_published``.

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

from meme_ops_db import migration_url, record_event
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

COMPONENT = "market_events"
MARKET_EVENT_SOURCES = ("baha", "manual", "plantao", "exchange_notice")
MARKET_EVENT_KINDS = (
    "listing",
    "delisting",
    "upgrade",
    "incident",
    "macro",
    "company",
    "narrative",
)
MARKET_EVENT_CONFIDENCES = ("confirmed", "reported", "rumor")
EX_USAGE, EX_REFUSED = 64, 65

__all__ = ["Refused", "insert_event", "main", "run"]


class Connection(Protocol):
    async def execute(self, statement: Any, parameters: Any = None, /) -> Any: ...


class Refused(Exception):
    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason


_INSERT = text(
    "INSERT INTO market_events (id, market_id, exchange, symbol, source, kind, title, url, "
    "  published_at, observed_at, confidence, notes, recorded_by) "
    "VALUES (gen_random_uuid(), "
    "  (SELECT (array_agg(m.id))[1] FROM markets m "
    "      JOIN exchanges e ON e.id = m.exchange_id "
    "     WHERE m.symbol = :symbol AND e.code = :exchange "
    "    HAVING count(*) = 1), "
    "  :exchange, :symbol, :source, :kind, :title, :url, :published_at, :observed_at, "
    "  :confidence, CAST(:notes AS jsonb), :recorded_by) "
    "ON CONFLICT (source, url, symbol) WHERE url IS NOT NULL DO NOTHING "
    "RETURNING id::text"
)
"""One row, with two guards worth reading.

**``market_id`` is filled only when the identity is unambiguous** — otherwise
``NULL``. Astra's review of T4.82 found the bug in the first version of this
sub-select, which matched the oldest ``markets`` row on the symbol alone: with
ZECUSDT listed on both Binance and Bybit, an item filed as Bybit would be
stamped with Binance's market id because Binance was catalogued first, and the
API would hand the screen a row whose ``exchange`` and ``market_id``
contradict each other. So the venue joins the match, and ``HAVING count(*) =
1`` makes the aggregate return no row — hence ``NULL`` — whenever the pair is
not uniquely identified: no ``--exchange`` given (``e.code = NULL`` matches
nothing), an unknown venue, or the symbol listed twice on it (a perpetual and
a spot listing). ``NULL`` is the honest answer there, which is why the column
is nullable at all; ``symbol``, not ``market_id``, is what the screen reads by.
``array_agg(...)[1]`` rather than ``max()``: Postgres has no ``max(uuid)``.

**``ON CONFLICT ... DO NOTHING``** on the partial unique makes a re-run
harmless; ``RETURNING`` then yields nothing, which is how :func:`run` knows to
report "already recorded" instead of writing an audit row that says "added".
The conflict target carries ``symbol`` (see ``ddl/market_events.py``): one
announcement naming two pairs is two rows, one per pair, and only a re-filing
of the *same* pair is a duplicate.

No value is ever interpolated into this statement — every input is a bound
parameter, and the sub-select is a literal."""


def _require_text(value: str | None, reason: str, detail: str) -> str:
    if value is None or not value.strip():
        raise Refused(reason, detail)
    return value.strip()


def _utc(value: datetime | None, field: str) -> datetime | None:
    """Tz-aware UTC, or a named refusal. Never a silent local-time reading."""
    if value is None:
        return None
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise Refused("naive_datetime", f"--{field} needs an offset (e.g. 2026-09-23T14:32Z)")
    return value.astimezone(UTC)


def _plan(fields: dict[str, Any]) -> str:
    published = fields["published_at"]
    return (
        f"add {fields['kind']} ({fields['confidence']}) on {fields['symbol']}"
        f"{'' if fields['exchange'] is None else '@' + fields['exchange']}: "
        f"{fields['title']!r}"
        f"\n  url={fields['url']}"
        f"\n  published_at={'unknown' if published is None else published.isoformat()}"
        f"  observed_at={fields['observed_at'].isoformat()}"
        f"\n  recorded_by={fields['recorded_by']} source={fields['source']}"
    )


async def insert_event(conn: Connection, **fields: Any) -> str | None:
    """The new row's id, or ``None`` when ``(source, url)`` already held one."""
    rows = (await conn.execute(_INSERT, fields)).scalars().all()
    return None if not rows else str(rows[0])


async def run(
    conn: Connection,
    *,
    symbol: str | None,
    exchange: str | None,
    kind: str,
    title: str | None,
    url: str | None,
    confidence: str,
    source: str,
    published_at: datetime | None,
    observed_at: datetime | None,
    notes: str | None,
    recorded_by: str | None,
    apply: bool,
) -> tuple[int, str]:
    """``(exit code, report)``. Writes only with ``add --apply``.

    Every refusal happens before the first statement, so a rejected run leaves
    the database exactly as it found it.
    """
    if kind not in MARKET_EVENT_KINDS:
        raise Refused("kind_unknown", f"{kind!r}; one of {MARKET_EVENT_KINDS}")
    if confidence not in MARKET_EVENT_CONFIDENCES:
        raise Refused("confidence_unknown", f"{confidence!r}; one of {MARKET_EVENT_CONFIDENCES}")
    if source not in MARKET_EVENT_SOURCES:
        raise Refused("source_unknown", f"{source!r}; one of {MARKET_EVENT_SOURCES}")
    resolved_symbol = _require_text(symbol, "symbol_required", "--symbol names the pair").upper()
    resolved_title = _require_text(title, "title_required", "--title carries the headline")
    resolved_by = _require_text(
        recorded_by, "recorded_by_required", "--by names who is registering this"
    )
    published = _utc(published_at, "published-at")
    observed = _utc(observed_at, "observed-at") or datetime.now(UTC)
    if published is not None and observed < published:
        raise Refused(
            "observed_before_published",
            f"observed {observed.isoformat()} < published {published.isoformat()}",
        )

    fields: dict[str, Any] = {
        "symbol": resolved_symbol,
        # Lower-cased (Astra): ``exchanges.code`` is lower-case, and the read's
        # ``exchange IS NULL OR exchange = :exchange`` is an exact match — a row
        # filed as "Binance" would be invisible on the ``/binance/...`` route
        # *and* would fail to resolve its ``market_id``.
        "exchange": None if exchange is None or not exchange.strip() else exchange.strip().lower(),
        "kind": kind,
        "title": resolved_title,
        "url": None if url is None or not url.strip() else url.strip(),
        "confidence": confidence,
        "source": source,
        "published_at": published,
        "observed_at": observed,
        "notes": json.dumps(json.loads(notes) if notes else {}),
        "recorded_by": resolved_by,
    }
    plan = _plan(fields)
    if not apply:
        return 0, plan + "\ndry-run: nothing written (add --apply)"

    event_id = await insert_event(conn, **fields)
    if event_id is None:
        return 0, plan + (
            f"\nalready recorded: ({fields['source']}, {fields['url']}) is in market_events; "
            "nothing written"
        )
    await record_event(
        conn,
        component=COMPONENT,
        level="info",
        event="added",
        message=(
            f"{event_id}: {fields['symbol']} {kind} ({confidence}) "
            f"{resolved_title!r} by {resolved_by}"
        ),
    )
    return 0, plan + f"\napplied: market_events {event_id}; system_events written"


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])  # type: ignore[union-attr]
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add", help="register one headline about a market")
    add.add_argument("--symbol", required=True, help="the pair, e.g. ZECUSDT")
    add.add_argument(
        "--exchange", default=None, help="the venue, when the item is about one; omit for macro"
    )
    add.add_argument("--kind", required=True, choices=MARKET_EVENT_KINDS)
    add.add_argument("--title", required=True)
    add.add_argument("--url", default=None)
    add.add_argument("--confidence", required=True, choices=MARKET_EVENT_CONFIDENCES)
    add.add_argument("--source", default="manual", choices=MARKET_EVENT_SOURCES)
    add.add_argument(
        "--published-at", default=None, help="ISO 8601 with offset; omit when the source is silent"
    )
    add.add_argument("--observed-at", default=None, help="ISO 8601 with offset, default now")
    add.add_argument("--notes", default=None, help="a JSON object")
    add.add_argument("--by", dest="recorded_by", required=True, help="who is registering this")
    add.add_argument("--apply", action="store_true")
    return parser.parse_args(argv)


def _instant(raw: str | None) -> datetime | None:
    return None if raw is None else datetime.fromisoformat(raw.replace("Z", "+00:00"))


async def _main(argv: Sequence[str]) -> int:
    args = _parse(argv)
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as conn, conn.begin():
            try:
                code, report = await run(
                    conn,
                    symbol=args.symbol,
                    exchange=args.exchange,
                    kind=args.kind,
                    title=args.title,
                    url=args.url,
                    confidence=args.confidence,
                    source=args.source,
                    published_at=_instant(args.published_at),
                    observed_at=_instant(args.observed_at),
                    notes=args.notes,
                    recorded_by=args.recorded_by,
                    apply=args.apply,
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
