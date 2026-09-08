"""``GET /api/v1/lab/shadow/{scoreboard,curve}`` — brief T3.18, extended T3.18b.

Global, no-RLS reads, same as ``routers/lab.py`` (DATABASE.md §16): any
authenticated user, no organization — Shadow Lab tables carry no
``organization_id`` and there is no schema change in this brief's scope to
add one. New router file rather than growing ``routers/lab.py`` past the
350-line budget; ``LabSession``/``resolve_as_of`` are shared verbatim from
there rather than duplicated.

T3.18b adds two blocks per scoreboard row (``replay``, ``replication``,
D14/D15 — the verdict and maturity stay computed on ``prospective`` alone,
untouched by either) and a ``cohort`` query param on the curve so the web can
draw a replay line dashed beside the live one.

T3.18c torna os dois blocos **opcionais** (``?include=replay,replication``,
padrão os dois) e pula a replicação inteira quando a versão não tem
``promising_at``: sem o carimbo o bloco é ``null`` por definição, e hoje isso
vale para todas as versões — eram cinco consultas e um bootstrap de mil
reamostras por linha para produzir um ``null``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, status

from hunter_api.errors import HunterError
from hunter_api.repositories.lab_replication import EMPTY_WINDOW, LabReplicationRepository
from hunter_api.repositories.lab_scoreboard import REPLAY_COHORT_WILDCARD, LabScoreboardRepository
from hunter_api.routers.lab import LabSession, resolve_as_of
from hunter_api.schemas.lab_curve import CurveOut
from hunter_api.schemas.lab_replication import ReplicationBlockOut
from hunter_api.schemas.lab_scoreboard import ReplayBlockOut, ScoreboardOut, ScoreboardRowOut
from hunter_api.services.lab_curve import OVERLAP_REASON, build_curve, overlapping_runs
from hunter_api.services.lab_replication import build_replication_block
from hunter_api.services.lab_scoreboard import build_scoreboard, build_scoreboard_row
from hunter_api.services.lab_scoreboard_replay import build_replay_block
from hunter_core.domain.enums import ShadowCohort

__all__ = ["router"]

router = APIRouter(prefix="/api/v1/lab/shadow", tags=["lab"])


INCLUDE_REPLAY = "replay"
INCLUDE_REPLICATION = "replication"
INCLUDE_ALL = (INCLUDE_REPLAY, INCLUDE_REPLICATION)


class InvalidCohortError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="invalid-cohort",
            title="Validation Error",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="'cohort' must be 'prospective', 'replay', or one exact shadow cohort.",
        )


class InvalidIncludeError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="invalid-include",
            title="Validation Error",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="'include' must be a comma-separated subset of 'replay,replication'.",
        )


class OverlappingReplayWindowsError(HunterError):
    """O coringa ``replay`` sobre corridas que se sobrepõem — T3.18c, item 10.

    Recusa, não soma: duas corridas sobre a mesma janela numa curva acumulada
    dobram o R. Quem quer a curva de uma delas pede ``cohort=replay:<uuid>``.
    """

    def __init__(self, clashes: list[tuple[str, str]]) -> None:
        pairs = "; ".join(f"{first} x {second}" for first, second in clashes[:3])
        super().__init__(
            type_slug=OVERLAP_REASON.replace("_", "-"),
            title="Validation Error",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"{OVERLAP_REASON}: as corridas de replay desta versao cobrem janelas "
                f"sobrepostas ({pairs}); peca uma corrida por vez (cohort=replay:<run_id>)."
            ),
        )


def _resolve_include(include: str) -> frozenset[str]:
    """``replay``, ``replication``, os dois (padrão) — nada mais.

    Um cliente que só desenha o cartão vivo não paga pelos dois blocos; um
    ``include`` vazio ou com nome desconhecido é ``422``, nunca "ignorei o que
    não entendi".
    """
    tokens = [token.strip() for token in include.split(",") if token.strip()]
    if not tokens or any(token not in INCLUDE_ALL for token in tokens):
        raise InvalidIncludeError
    return frozenset(tokens)


def _resolve_curve_cohort(cohort: str) -> str:
    """``prospective`` (default), ``replay`` (every run of this version at
    once — brief T3.18b, item 3) or one exact cohort
    (``ShadowCohort.is_valid``: ``replay:<uuid>`` or
    ``replication:<parent>:<k>``). Anything else is a ``422``, the same shape
    ``InvalidAsOfError`` uses for a malformed ``as_of``.
    """
    if cohort in (ShadowCohort.PROSPECTIVE, REPLAY_COHORT_WILDCARD) or ShadowCohort.is_valid(
        cohort
    ):
        return cohort
    raise InvalidCohortError


@router.get("/scoreboard", response_model=ScoreboardOut, summary="Shadow Lab version scoreboard")
async def get_scoreboard(
    session: LabSession,
    as_of: datetime | None = None,
    include: str = ",".join(INCLUDE_ALL),
) -> ScoreboardOut:
    resolved_as_of = resolve_as_of(as_of)
    wanted = _resolve_include(include)
    repo = LabScoreboardRepository(session)
    replication_repo = LabReplicationRepository(session)
    versions = await repo.versions_with_signals(resolved_as_of)
    rows: list[ScoreboardRowOut] = []
    for meta in versions:
        version_rows = await repo.rows_for(meta.id, resolved_as_of)
        replay_block = (
            await _replay_block(repo, meta.id, resolved_as_of) if INCLUDE_REPLAY in wanted else None
        )
        replication_block = (
            await _replication_block(replication_repo, meta.id, resolved_as_of)
            if INCLUDE_REPLICATION in wanted
            else None
        )
        rows.append(
            build_scoreboard_row(
                meta,
                version_rows,
                resolved_as_of,
                replay=replay_block,
                replication=replication_block,
            )
        )
    return build_scoreboard(as_of=resolved_as_of, rows=rows)


async def _replay_block(
    repo: LabScoreboardRepository, version_id: uuid.UUID, as_of: datetime
) -> ReplayBlockOut | None:
    replay_rows = await repo.rows_for(version_id, as_of, cohort=REPLAY_COHORT_WILDCARD)
    runs_summary = await repo.replay_runs_summary(version_id, as_of=as_of)
    return build_replay_block(rows=replay_rows, runs=runs_summary, as_of=as_of)


async def _replication_block(
    repo: LabReplicationRepository, version_id: uuid.UUID, as_of: datetime
) -> ReplicationBlockOut | None:
    """O caminho barato primeiro (T3.18c, item 8).

    Sem ``promising_at`` não há protocolo e o bloco é ``null`` — então nem a
    população do pai, nem as irmãs, nem os replays delas são carregados.
    """
    promising_at = await repo.promising_at(version_id)
    if promising_at is None:
        return None
    parent_outcomes = await repo.parent_outcomes(version_id, as_of=as_of)
    siblings_meta = await repo.siblings(version_id)
    windows = await repo.replay_windows([item.id for item in siblings_meta], as_of=as_of)
    siblings = [
        await repo.sibling_population(
            sibling, version_id, as_of=as_of, replay_window=windows.get(sibling.id, EMPTY_WINDOW)
        )
        for sibling in siblings_meta
    ]
    return build_replication_block(
        version_id=version_id,
        promising_at=promising_at,
        parent_outcomes=parent_outcomes,
        siblings=siblings,
        registered_seed=await repo.registered_seed(version_id),
    )


@router.get("/curve", response_model=CurveOut, summary="Shadow Lab cumulative net-R curve")
async def get_curve(
    session: LabSession,
    version_id: uuid.UUID,
    as_of: datetime | None = None,
    cohort: str = ShadowCohort.PROSPECTIVE,
) -> CurveOut:
    resolved_as_of = resolve_as_of(as_of)
    resolved_cohort = _resolve_curve_cohort(cohort)
    repo = LabScoreboardRepository(session)
    if resolved_cohort == REPLAY_COHORT_WILDCARD:
        runs = await repo.replay_runs_summary(version_id, as_of=resolved_as_of)
        clashes = overlapping_runs(runs.windows)
        if clashes:
            raise OverlappingReplayWindowsError(clashes)
    rows = await repo.rows_for(version_id, resolved_as_of, cohort=resolved_cohort)
    return build_curve(
        strategy_version_id=version_id, rows=rows, as_of=resolved_as_of, cohort=resolved_cohort
    )
