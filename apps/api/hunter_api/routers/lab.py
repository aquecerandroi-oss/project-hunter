"""``GET /api/v1/lab/shadow/{summary,signals,versions}`` — contract-S3-lab.md.

Global, no-RLS reads (DATABASE.md §16): any authenticated user, no
organization. Postgres unreachable is a ``503`` here, not the generic ``500``
``ProblemDetailsMiddleware`` would otherwise build — the same shape
``/system/workers`` uses for a Redis outage.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.exc import OperationalError

from hunter_api.auth.rbac import CurrentPrincipal
from hunter_api.deps import get_session_factory
from hunter_api.errors import HunterError
from hunter_api.repositories.base import MAX_PAGE_SIZE, clamp_page_size
from hunter_api.repositories.lab_signals import LabSignalsRepository
from hunter_api.repositories.lab_summary import LabSummaryRepository
from hunter_api.repositories.lab_versions import LabVersionsRepository
from hunter_api.schemas.lab_signals import SignalsPage
from hunter_api.schemas.lab_summary import SummaryOut, VersionSummaryOut
from hunter_api.schemas.lab_versions import VersionsOut
from hunter_api.services.lab_signals import build_signals_page
from hunter_api.services.lab_summary import build_summary, build_version_summary, window_since
from hunter_api.services.lab_versions import build_versions
from hunter_core.db.session import user_session
from hunter_core.domain.enums import (
    SHADOW_COHORT_PATTERN,
    OutcomeResult,
    ShadowCohort,
    ShadowTrackingState,
)
from hunter_core.domain.types import ensure_utc, utcnow
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/lab/shadow", tags=["lab"])

_WindowParam = Literal["7d", "30d", "all"]


class LabUnavailableError(HunterError):
    """(brief S3-lab-api) Postgres unreachable while reading Shadow Lab data."""

    def __init__(self) -> None:
        super().__init__(
            type_slug="lab-unavailable",
            title="Service Unavailable",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Shadow Lab data is temporarily unavailable.",
        )


class InvalidAsOfError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="invalid-as-of",
            title="Validation Error",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="'as_of' must be a timezone-aware UTC timestamp.",
        )


async def lab_session(
    request: Request, principal: CurrentPrincipal
) -> AsyncGenerator[AsyncSession, None]:
    """Authenticated, organization-less (research is global, DATABASE.md §16).

    A dedicated dependency rather than the shared ``PrincipalSession``: this
    router is the only one that must turn a connection failure into a ``503``
    instead of letting it fall through to the generic 500.

    **Formerly a known gap (Astra, diff review, must-fix 2), now closed:**
    ``CurrentPrincipal`` above resolves *before* this function's ``try`` runs,
    and that resolution reads Postgres too
    (``hunter_api.auth.principal.PrincipalResolver.resolve``). A connection
    failure during that read used to escape as a generic 500 — a systemic
    property of every authenticated route, not something this router's own
    dependency could fix. ``PrincipalResolver.resolve`` now carries its own
    ``(OperationalError, OSError)`` guard and raises
    ``auth.principal.PrincipalUnavailableError`` (``.../service-unavailable``),
    so that failure is a ``503`` before this function ever runs. What this
    ``except`` still catches: a connection lost *after* authentication
    succeeds, whether while opening this router's own transaction or during a
    query a route runs against it — the scenario the brief's "Postgres fora ->
    503" is about. ``OSError`` is included alongside SQLAlchemy's
    ``OperationalError`` because a failure at the driver/socket level does not
    always get wrapped before it surfaces.
    """
    try:
        async with user_session(get_session_factory(request), principal.user_id) as session:
            yield session
    except (OperationalError, OSError) as exc:
        logger.error("lab_postgres_unavailable", exc_info=exc)
        raise LabUnavailableError from exc


LabSession = Annotated["AsyncSession", Depends(lab_session)]
CohortParam = Annotated[str, Query(pattern=SHADOW_COHORT_PATTERN)]


def _resolve_as_of(as_of: datetime | None) -> datetime:
    """``utcnow()`` by default; a caller-supplied ``as_of`` must be tz-aware.

    Astra, diff review, must-fix 3: a naive ``as_of`` compared against the
    tz-aware ``exit_ts`` inside the maturity gate (``lab_summary_metrics.py``)
    raises ``TypeError`` instead of a clean 422.
    """
    if as_of is None:
        return utcnow()
    try:
        return ensure_utc(as_of)
    except ValueError:
        raise InvalidAsOfError from None


@router.get("/versions", response_model=VersionsOut, summary="Shadow strategy version catalogue")
async def list_versions(session: LabSession) -> VersionsOut:
    rows = await LabVersionsRepository(session).list_all()
    return build_versions(rows)


@router.get("/summary", response_model=SummaryOut, summary="Shadow Lab performance summary")
async def get_summary(
    session: LabSession,
    window: _WindowParam = "30d",
    as_of: datetime | None = None,
    cohort: CohortParam = ShadowCohort.PROSPECTIVE,
) -> SummaryOut:
    resolved_as_of = _resolve_as_of(as_of)
    since = window_since(window, resolved_as_of)
    repo = LabSummaryRepository(session)
    versions_meta = await repo.activated_versions()
    summaries: list[VersionSummaryOut] = []
    for meta in versions_meta:
        rows = await repo.outcomes_for(meta.id, cohort=cohort, since=since, as_of=resolved_as_of)
        summaries.append(build_version_summary(meta, rows, resolved_as_of))
    return build_summary(as_of=resolved_as_of, window=window, cohort=cohort, versions=summaries)


@router.get(
    "/signals", response_model=SignalsPage, summary="Shadow Lab decisions and tracked outcomes"
)
async def list_signals(
    session: LabSession,
    strategy_version_id: uuid.UUID | None = None,
    market: Annotated[str | None, Query(max_length=32)] = None,
    tracking_state: ShadowTrackingState | None = None,
    result: OutcomeResult | None = None,
    cohort: CohortParam = ShadowCohort.PROSPECTIVE,
    cursor: str | None = None,
    limit: Annotated[int | None, Query(ge=1, le=MAX_PAGE_SIZE)] = None,
    include: Annotated[list[str] | None, Query()] = None,
) -> SignalsPage:
    rows, next_cursor = await LabSignalsRepository(session).list_page(
        strategy_version_id=strategy_version_id,
        market=market,
        tracking_state=tracking_state,
        result=result,
        cohort=cohort,
        cursor=cursor,
        limit=clamp_page_size(limit),
    )
    include_envelope = include is not None and "envelope" in include
    return build_signals_page(rows, next_cursor, include_envelope=include_envelope)
