"""Recompute funding for closed Shadow Lab outcomes stuck at ``R_net = null`` — S2-funding.

    uv run python infra/scripts/recompute_funding.py --dry-run
    uv run python infra/scripts/recompute_funding.py --apply --reason "S2-funding: slot identity"

The Lab is append-honest (SHADOW-LAB.md "Decisão conjunta" §6): a closed
outcome is never rewritten by a scheduled or automatic process. This script is
that append, run by a human, after a fix to
:mod:`hunter_strategy_worker.funding` (identity by nearest-within-tolerance
match, not exact timestamp equality — EXP-0001-momentum-v1.md H2, 69 of 73
``funding_missing`` outcomes had a real ``funding_rates`` row less than 2 s
from the instant the old code required exactly).

It lists every **terminal** ``signal_outcomes`` row whose ``r_multiple`` is
``NULL`` because funding could not be established, and recomputes the funding
reading with the *current* code against the *stored* inputs — ``entry_ts``,
``exit_ts``, ``virtual_entry``, ``virtual_stop``, ``exit_price``,
``meta.assumed_costs`` and ``meta.progress`` (``exit_at_open``/
``exit_bar_open``, needed for the same ambiguous-exit guard ``settle()``
applies) — never from memory or from re-walking the bars. Only ``--apply``
writes, and only the rows whose funding now actually resolves: ``r_multiple``
and ``meta.funding`` are rewritten, ``meta.r_ex_funding`` is untouched (it was
never wrong — it never depended on funding). ``meta.funding.reason`` is left
``null`` (a query counting a non-null reason as "funding unavailable" must not
keep seeing a fixed outcome as broken); the audit trail lives in
``meta.funding.previous`` (the whole prior ``funding`` object, never erased),
``recomputed_at`` and ``recompute_reason``. A row still unestablishable after
the fix (a genuine ``funding_schedule_unknown``, an ambiguous exit, or rows
that disagree) is left exactly as it was.

Connects with ``DATABASE_URL_MIGRATIONS`` (direct, never the pooler), like
``infra/scripts/seed.py`` and ``infra/scripts/activate_strategy_version.py``:
this writes a table no tenant role should touch, and shadow research has no
``organization_id`` to set ``app.current_org`` for in the first place
(DATABASE.md §1.1).
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from hunter_core.settings import Settings
from hunter_core.strategies.canonical import canonical_json
from hunter_core.strategies.envelope import AssumedCosts
from hunter_strategy_worker.funding import MATCH_TOLERANCE, Settlement, resolve_funding
from hunter_strategy_worker.pricing import r_net

_CADENCE_LOOKBACK = timedelta(days=3)
"""Must match ``hunter_strategy_worker.settle._CADENCE_LOOKBACK``: the window
has to be wide enough for :func:`resolve_funding` to read the market's own
settlement cadence, exactly as ``settle()`` does, or the recompute would not
match what a fresh close would have produced."""

_DEFAULT_REASON = (
    "S2-funding: settlement re-identified by nearest-within-tolerance match "
    "against funding_rates, not exact timestamp equality (EXP-0001 H2)"
)

_CANDIDATES_SQL = text(
    "SELECT o.signal_id, o.entry_ts, o.exit_ts, o.virtual_entry, o.virtual_stop, "
    "o.exit_price, o.meta, s.market_id, m.symbol, e.code AS exchange "
    "FROM signal_outcomes o "
    "JOIN agent_signals s ON s.id = o.signal_id "
    "JOIN markets m ON m.id = s.market_id "
    "JOIN exchanges e ON e.id = m.exchange_id "
    "WHERE o.tracking_state = 'terminal' AND o.r_multiple IS NULL "
    "AND o.meta ? 'funding' AND o.meta->'funding'->>'reason' IS NOT NULL "
    "ORDER BY o.exit_ts"
)

_FUNDING_SQL = text(
    "SELECT funding_time, rate, mark_price FROM funding_rates "
    "WHERE market_id = :market_id AND funding_time >= :since AND funding_time <= :until "
    "ORDER BY funding_time"
)

_UPDATE_SQL = text(
    "UPDATE signal_outcomes SET r_multiple = :r_multiple, "
    "meta = jsonb_set("
    "  jsonb_set(meta, '{funding}', CAST(:funding AS jsonb)), "
    "  '{r_net_reason}', 'null'::jsonb"
    ") "
    "WHERE signal_id = :signal_id AND tracking_state = 'terminal' AND r_multiple IS NULL"
)


@dataclass(frozen=True, slots=True)
class Candidate:
    """One terminal outcome whose funding could not be established, and enough
    of its frozen inputs to recompute it the same way ``settle()`` would."""

    signal_id: Any
    market_id: Any
    symbol: str
    exchange: str
    entry_ts: datetime
    exit_ts: datetime
    virtual_entry: Decimal
    virtual_stop: Decimal
    exit_price: Decimal
    costs: AssumedCosts
    ambiguous_from: datetime | None
    old_funding: dict[str, Any]
    """The prior ``meta.funding`` object verbatim — kept so ``--apply`` can
    nest it under the new ``meta.funding.previous`` instead of erasing the
    evidence of what the bug actually produced (Astra, S2-funding review,
    round 2 must-fix 5)."""


@dataclass(frozen=True, slots=True)
class Recomputed:
    """The result of recomputing one candidate."""

    candidate: Candidate
    r_multiple: Decimal | None
    funding_meta: dict[str, Any]
    charged_at: tuple[datetime, ...]


def _load_candidate(row: Any) -> Candidate | None:
    meta: dict[str, Any] = row.meta or {}
    progress: dict[str, Any] | None = meta.get("progress")
    costs_raw: dict[str, Any] | None = meta.get("assumed_costs")
    if progress is None or costs_raw is None or row.entry_ts is None or row.exit_ts is None:
        return None
    exit_at_open = bool(progress.get("exit_at_open", True))
    exit_bar_open: str | None = progress.get("exit_bar_open")
    ambiguous_from = (
        None if exit_at_open or exit_bar_open is None else datetime.fromisoformat(exit_bar_open)
    )
    old_funding: dict[str, Any] = meta.get("funding") or {}
    return Candidate(
        signal_id=row.signal_id,
        market_id=row.market_id,
        symbol=row.symbol,
        exchange=row.exchange,
        entry_ts=row.entry_ts,
        exit_ts=row.exit_ts,
        virtual_entry=row.virtual_entry,
        virtual_stop=row.virtual_stop,
        exit_price=row.exit_price,
        costs=AssumedCosts.model_validate(costs_raw),
        ambiguous_from=ambiguous_from,
        old_funding=old_funding,
    )


async def _candidates(conn: AsyncConnection) -> list[Candidate]:
    rows = (await conn.execute(_CANDIDATES_SQL)).all()
    out: list[Candidate] = []
    for row in rows:
        candidate = _load_candidate(row)
        if candidate is None:
            print(f"SKIPPED {row.signal_id}: missing progress/assumed_costs/entry_ts/exit_ts")
            continue
        out.append(candidate)
    return out


async def _funding_history(conn: AsyncConnection, candidate: Candidate) -> list[Settlement]:
    rows = (
        await conn.execute(
            _FUNDING_SQL,
            {
                "market_id": candidate.market_id,
                "since": candidate.entry_ts - _CADENCE_LOOKBACK,
                # +MATCH_TOLERANCE, exactly like settle.py: a real row just
                # after exit_ts can be the other half of a boundary-straddling
                # cluster (Astra, S2-funding review, round 4 must-fix 1).
                "until": candidate.exit_ts + MATCH_TOLERANCE,
            },
        )
    ).all()
    return [
        Settlement(
            funding_time=row.funding_time,
            rate=Decimal(row.rate),
            mark_price=None if row.mark_price is None else Decimal(row.mark_price),
        )
        for row in rows
    ]


def _recompute(candidate: Candidate, history: list[Settlement]) -> Recomputed:
    reading = resolve_funding(
        history,
        entry_ts=candidate.entry_ts,
        exit_ts=candidate.exit_ts,
        ambiguous_from=candidate.ambiguous_from,
    )
    r_multiple = None
    if reading.per_unit is not None:
        r_multiple = r_net(
            entry=candidate.virtual_entry,
            exit_=candidate.exit_price,
            stop=candidate.virtual_stop,
            costs=candidate.costs,
            funding_per_unit=reading.per_unit,
        )
    return Recomputed(
        candidate=candidate,
        r_multiple=r_multiple,
        funding_meta=reading.to_jsonable(),
        charged_at=reading.charged_at,
    )


def _report_line(result: Recomputed) -> str:
    c = result.candidate
    old_reason = c.old_funding.get("reason")
    slot = ", ".join(t.isoformat() for t in result.charged_at) or old_reason or "-"
    after = "null (still unestablishable)" if result.r_multiple is None else str(result.r_multiple)
    return f"{c.signal_id}  {c.exchange}:{c.symbol}  slot={slot}  R_net before=null after={after}"


async def _apply(conn: AsyncConnection, result: Recomputed, *, reason: str) -> bool:
    """Write the recomputed row; ``False`` if a concurrent run already did.

    ``meta.funding.reason`` is left exactly as :func:`resolve_funding` produced
    it (``null``, since this is only called when the reading resolved) — a
    query that treats a non-null ``reason`` as "funding unavailable" must not
    start seeing a freshly-fixed outcome as still broken. The audit trail lives
    in new keys instead: ``previous`` (the whole prior ``meta.funding``, so the
    bug's own output is never erased), ``recomputed_at`` and ``recompute_reason``
    (Astra, S2-funding review, round 2 must-fix 4 and 5).
    """
    funding_meta = dict(result.funding_meta)
    funding_meta["previous"] = result.candidate.old_funding
    funding_meta["recomputed_at"] = datetime.now(UTC).isoformat()
    funding_meta["recompute_reason"] = reason
    payload = json.loads(canonical_json(funding_meta))
    outcome = await conn.execute(
        _UPDATE_SQL,
        {
            "signal_id": result.candidate.signal_id,
            "r_multiple": result.r_multiple,
            "funding": json.dumps(payload),
        },
    )
    return outcome.rowcount > 0


async def _process(
    open_tx: Callable[[], AbstractAsyncContextManager[Any]], *, apply: bool, reason: str
) -> tuple[int, int, int]:
    """Recompute every candidate, **one transaction per row**.

    ``open_tx`` opens a fresh transaction (``engine.begin()`` in production, a
    role session in tests). The UPDATE is idempotent per row (``WHERE
    r_multiple IS NULL``), so committing row by row is safe to re-run and
    means a failure at row N — a legacy ``assumed_costs`` shape, an operator's
    Ctrl-C — leaves rows 1..N-1 committed and visible, matching what the
    console already reported for them (code review of d878fd6, finding 1: a
    single run-wide transaction rolled every printed line back and held row
    locks on ``signal_outcomes`` for the whole run). Returns
    ``(candidates, resolved, applied)``.
    """
    async with open_tx() as conn:
        candidates = await _candidates(conn)
    print(f"{len(candidates)} terminal outcome(s) with r_multiple null due to funding")
    resolved = 0
    applied = 0
    for candidate in candidates:
        async with open_tx() as conn:
            history = await _funding_history(conn, candidate)
            result = _recompute(candidate, history)
            print(_report_line(result))
            if result.r_multiple is None:
                continue  # reported, never written — no audit trail on an unresolved row
            resolved += 1
            if apply and await _apply(conn, result, reason=reason):
                applied += 1
    return len(candidates), resolved, applied


async def _run(args: argparse.Namespace) -> int:
    secret = Settings().database_url_migrations
    if secret is None or not secret.get_secret_value():
        raise SystemExit("DATABASE_URL_MIGRATIONS is not configured")
    url = secret.get_secret_value()
    if not url.startswith("postgresql+"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url, connect_args={"statement_cache_size": 0})
    apply = args.apply and not args.dry_run
    try:
        total, resolved, applied = await _process(engine.begin, apply=apply, reason=args.reason)
        mode = "applied" if apply else "dry-run"
        summary = f"{mode}: {resolved}/{total} outcome(s) now resolve"
        if apply:
            summary += f"; {applied} row(s) written"
        print(summary)
    finally:
        await engine.dispose()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="list what would change, write nothing (default)"
    )
    parser.add_argument("--apply", action="store_true", help="write the recomputed rows")
    parser.add_argument(
        "--reason",
        default=_DEFAULT_REASON,
        help="audit reason stored in meta.funding.recompute_reason",
    )
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
