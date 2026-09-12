"""``/api/v1/orgs/{org_id}/meme/tests`` — the complete record of every test
on the desk (T4.13), read-only, VIEWER+.

Three reads over the same assembly: the page (``GET /tests``, keyset on
``entry_at DESC, id DESC`` inside one Brasília day), the export
(``GET /tests.csv``, the whole day, ``services/meme_tests_csv.py``) and one
bet's record with the curve between its entry and its exit
(``GET /tests/{bet_id}``). Nothing here writes; nothing here executes.

The observed wallet's REAL positions (T4.12) are read by table name and come
back as ``real_items`` on the first page and merged into the CSV; when the
table does not exist yet the payload says ``sources.wallets = "não observada"``.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from hunter_api.auth.rbac import OrgContext, require_org
from hunter_api.deps import OrgSession
from hunter_api.repositories.base import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    decode_cursor,
    encode_cursor,
)
from hunter_api.repositories.meme_tests import BetRecord, MemeTestsRepository
from hunter_api.schemas.meme_tests import (
    TestCurvePointOut,
    TestDetailOut,
    TestRowOut,
    TestsListOut,
)
from hunter_api.services.meme_desk_common import BetNotFoundError
from hunter_api.services.meme_tests import (
    brasilia_day,
    brasilia_day_bounds,
    build_sources,
    build_test_row,
    build_totals,
)
from hunter_api.services.meme_tests_csv import CSV_MAX_ROWS, csv_filename, render_tests_csv
from hunter_api.services.meme_tests_real import real_rows_out
from hunter_core.domain.enums import OrganizationRole
from hunter_core.domain.types import utcnow

__all__ = ["CURVE_MARGIN", "CURVE_MAX_POINTS", "REAL_MAX_ROWS", "router"]

router = APIRouter(prefix="/api/v1/orgs/{org_id}/meme", tags=["meme"])

ViewerOrg = Annotated[OrgContext, Depends(require_org(OrganizationRole.VIEWER))]
_Limit = Annotated[int | None, Query(ge=1, le=MAX_PAGE_SIZE)]
_RuleSet = Annotated[str | None, Query(alias="rule_set", max_length=64)]

CURVE_MARGIN = timedelta(minutes=5)
"""The detail's curve runs from five minutes before the entry to five after
the exit (or the last mark), so both marks sit inside the drawn span."""
CURVE_MAX_POINTS = 600
REAL_MAX_ROWS = 500


async def _rows_out(repo: MemeTestsRepository, page: list[BetRecord]) -> list[TestRowOut]:
    pairs = {
        (row.bet.mint, row.proposal.features_end_time)
        for row in page
        if row.proposal is not None and row.proposal.features_end_time is not None
    }
    features = await repo.features_at(pairs)
    out: list[TestRowOut] = []
    for row in page:
        key = (
            (row.bet.mint, row.proposal.features_end_time)
            if row.proposal is not None and row.proposal.features_end_time is not None
            else None
        )
        out.append(build_test_row(row, features.get(key) if key is not None else None))
    return out


def _resolve_day(day: date | None, now: datetime) -> tuple[date, datetime, datetime]:
    chosen = day or brasilia_day(now)
    start, end = brasilia_day_bounds(chosen)
    return chosen, start, end


@router.get(
    "/tests",
    response_model=TestsListOut,
    summary="Every test of a Brasília day: entry, exit, PnL, R, leg and what the Lab said",
)
async def list_tests(
    context: ViewerOrg,
    session: OrgSession,
    day: date | None = None,
    rule_set: _RuleSet = None,
    limit: _Limit = None,
    cursor: str | None = None,
) -> TestsListOut:
    now = utcnow()
    chosen, start, end = _resolve_day(day, now)
    page_size = limit or DEFAULT_PAGE_SIZE
    repo = MemeTestsRepository(session)
    decoded = decode_cursor(cursor)
    rows = await repo.list_day_bets(
        day_start=start, day_end=end, rule_set=rule_set, limit=page_size + 1, cursor=decoded
    )
    has_more = len(rows) > page_size
    page = rows[:page_size]
    next_cursor = (
        encode_cursor(page[-1].bet.entry_at, page[-1].bet.id) if has_more and page else None
    )
    items = await _rows_out(repo, page)
    if decoded is None and rule_set is None:
        wallets = await repo.wallet_positions(day_start=start, day_end=end, limit=REAL_MAX_ROWS)
        real_items = real_rows_out(wallets.rows)
        wallets_source = wallets.source
    else:
        real_items, wallets_source = (
            [],
            (await repo.wallet_positions(day_start=start, day_end=end, limit=1)).source,
        )
    totals = await repo.day_totals(day_start=start, day_end=end, rule_set=rule_set)
    indeterminate = await repo.indeterminate_totals(day_start=start, day_end=end, rule_set=rule_set)
    names = await repo.day_rule_set_names(day_start=start, day_end=end)
    names.extend(sorted({r.rule_set.label for r in real_items}))
    return TestsListOut(
        server_now=now,
        day=chosen,
        day_start=start,
        day_end=end,
        rule_set=rule_set,
        rule_sets=names,
        totals=build_totals(totals, real_rows=len(real_items), indeterminate=indeterminate),
        sources=build_sources(wallets_source),
        items=items,
        real_items=real_items,
        next_cursor=next_cursor,
    )


@router.get(
    "/tests.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv; charset=utf-8": {}}}},
    summary="The same record as a CSV for Excel in pt-BR (UTF-8 with BOM, ';', Brasília)",
)
async def export_tests_csv(
    context: ViewerOrg,
    session: OrgSession,
    day: date | None = None,
    rule_set: _RuleSet = None,
) -> Response:
    now = utcnow()
    chosen, start, end = _resolve_day(day, now)
    repo = MemeTestsRepository(session)
    rows = await repo.list_day_bets(
        day_start=start, day_end=end, rule_set=rule_set, limit=CSV_MAX_ROWS + 1, cursor=None
    )
    truncated = len(rows) > CSV_MAX_ROWS
    items = await _rows_out(repo, rows[:CSV_MAX_ROWS])
    if rule_set is None:
        wallets = await repo.wallet_positions(day_start=start, day_end=end, limit=REAL_MAX_ROWS)
        items.extend(real_rows_out(wallets.rows))
    items.sort(key=lambda r: (r.entry.at, r.id), reverse=True)
    body = render_tests_csv(items, truncated=truncated)
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{csv_filename(chosen.isoformat())}"'
        },
    )


@router.get(
    "/tests/{bet_id}",
    response_model=TestDetailOut,
    summary="One bet's record with the curve between its entry and its exit",
)
async def get_test(context: ViewerOrg, session: OrgSession, bet_id: uuid.UUID) -> TestDetailOut:
    now = utcnow()
    repo = MemeTestsRepository(session)
    row = await repo.get_bet(bet_id)
    if row is None:
        raise BetNotFoundError
    out = (await _rows_out(repo, [row]))[0]
    last = out.exit.at or now
    curve_from = out.entry.at - CURVE_MARGIN
    curve_to = last + CURVE_MARGIN
    points = await repo.curve_between(
        row.bet.mint, start=curve_from, end=curve_to, limit=CURVE_MAX_POINTS
    )
    return TestDetailOut(
        server_now=now,
        row=out,
        curve=[
            TestCurvePointOut(
                observed_at=p.observed_at, source=p.source, mcap_sol=p.mcap_sol, complete=p.complete
            )
            for p in points
        ],
        curve_from=curve_from,
        curve_to=curve_to,
    )
