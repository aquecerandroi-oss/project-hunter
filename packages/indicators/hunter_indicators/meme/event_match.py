"""The event <-> coin matching rule (T4.26b) -- pure, no IO, so the symbol/name/
handle/avoid cases are unit-tested without a database. Shared between the
worker's per-minute job (``hunter_meme_worker.events_repo``) and the audited
backfill script (``infra/scripts/meme_event.py rematch``) -- a pure gate
belongs in this package, not in either caller's own service tree (the
convention ``infra/scripts/meme_ops_db.py`` already states: a script must not
import another service's package for shared logic).

**Explicit, per the brief.** A coin matches an event when its symbol is one
of the event's tickers (case-insensitive, ``$`` stripped), *or* its name
matches a word-boundary regex built from the event's tickers and keywords
(so ``ARC`` also catches "Circle" through the keyword, and never matches
"march"), *or* its twitter handle equals the event's own handle. Tickers
come from ``symbol_hint`` (0041, unchanged) *and* ``notes->'tickers'``
(T4.26b, for an event whose narrative needs more than one ticker -- KB-0100's
own list for Circle Arc was ``ARC|ARCH|ARCC|CIRCLE|USDC``); keywords come
from ``notes->'keywords'`` only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

__all__ = [
    "MATCH_AVOID",
    "MATCH_BUY",
    "EventHints",
    "event_hints",
    "event_match_kind",
    "is_match",
]

MATCH_BUY = "buy"
MATCH_AVOID = "avoid"


@dataclass(frozen=True, slots=True)
class EventHints:
    """What one event is looking for, normalized once per tick."""

    tickers: frozenset[str]
    keywords: tuple[str, ...]
    handle: str | None


def _normalize_ticker(raw: str) -> str:
    return raw.strip().lstrip("$").upper()


def event_hints(
    *, symbol_hint: str | None, handle_hint: str | None, notes: dict[str, Any] | None
) -> EventHints:
    """``symbol_hint``/``handle_hint`` (0041) plus ``notes->'tickers'``/
    ``notes->'keywords'`` (T4.26b) -- additive, so an event registered before
    this revision still matches exactly as it did."""
    tickers: set[str] = {_normalize_ticker(symbol_hint)} if symbol_hint else set()
    for raw in (notes or {}).get("tickers") or ():
        ticker = _normalize_ticker(str(raw))
        if ticker:
            tickers.add(ticker)
    keywords = tuple(
        str(raw).strip().lower() for raw in (notes or {}).get("keywords") or () if str(raw).strip()
    )
    handle = handle_hint.lstrip("@").strip().lower() if handle_hint else None
    return EventHints(tickers=frozenset(tickers), keywords=keywords, handle=handle or None)


def event_match_kind(notes: dict[str, Any] | None) -> str:
    """``notes->>'action' = 'avoid'`` marks every coin this event names as a
    warning, not a buy signal (KB-0100 event 8, the clone viveiro "aviso")."""
    return MATCH_AVOID if (notes or {}).get("action") == "avoid" else MATCH_BUY


def _name_pattern(hints: EventHints) -> re.Pattern[str] | None:
    words = sorted({*hints.tickers, *hints.keywords})
    words = [w for w in words if w]
    if not words:
        return None
    return re.compile(rf"\b(?:{'|'.join(re.escape(w) for w in words)})\b", re.IGNORECASE)


def is_match(
    hints: EventHints, *, symbol: str | None, name: str | None, twitter: str | None
) -> bool:
    if symbol and _normalize_ticker(symbol) in hints.tickers:
        return True
    pattern = _name_pattern(hints)
    if pattern is not None and name and pattern.search(name):
        return True
    if hints.handle and twitter:
        escaped = re.escape(hints.handle)
        if re.search(rf"(?:^|/)@?{escaped}(?:/|$)", twitter.lower()):
            return True
    return False
