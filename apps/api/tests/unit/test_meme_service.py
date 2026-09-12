"""``services/meme.py`` — pure mapping/derivation and the overview's two
branches (T4.3). No DB, no network: the passthrough branch is tested against
the real, dated fixture from T4.1's live capture
(``packages/exchange-adapters/tests/fixtures/pumpfun/mayhem_overview_raw.json``),
never an invented shape. Field names follow the frozen contract
(``.claude/state/notes-T4.2.md`` §"contrato"): ``completed_at``/``migrated_at``
timestamps, not a ``complete`` boolean; ``snapshot_observed_at``/``snapshot_source``.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from hunter_api.repositories.meme import MemeGraduationMatrixRow, MemeRepository, MemeTokenRow
from hunter_api.schemas.meme import GraduationsOut
from hunter_api.services.meme import (
    build_graduation_matrix_out,
    build_overview,
    build_token_out,
    derive_state,
)
from hunter_exchanges.pumpfun.models import NormalizedMayhemOverview
from hunter_exchanges.pumpfun.rest import PumpFunRestClient

pytestmark = pytest.mark.unit

FIXTURE = (
    Path(__file__).resolve().parents[4]
    / "packages"
    / "exchange-adapters"
    / "tests"
    / "fixtures"
    / "pumpfun"
    / "mayhem_overview_raw.json"
)


def _row(**overrides: Any) -> MemeTokenRow:
    base: dict[str, Any] = {
        "mint": "Fh42kAfy27CGoUA8CgFwpTGMubzndaAyTy2gghu5pump",
        "name": "bum bum",
        "symbol": "bam bum",
        "creator": "s9uu4shkYUQUmnWN2jkwgA2Nbg2Rmv7vUprtjy71xgP",
        "created_at": datetime(2026, 9, 12, 0, 0, tzinfo=UTC),
        "mayhem_enabled": True,
        "mayhem_state": "active",
        "completed_at": None,
        "migrated_at": None,
        "mcap_sol": Decimal("9.05"),
        "curve_progress_pct": Decimal("0.0006"),
        "snapshot_observed_at": datetime(2026, 9, 12, 0, 5, tzinfo=UTC),
        "snapshot_source": "pumpfun_rest",
        "rest_complete_seen_at": None,
        "curve_filled_seen_at": None,
        "graduated_board_seen_at": None,
        "pool_created_at": None,
        "pool_created_source": None,
        "progress_denominator_source": None,
    }
    base.update(overrides)
    return MemeTokenRow(**base)


MATRIX_DAY = date(2026, 9, 12)


def _matrix_row(**overrides: Any) -> MemeGraduationMatrixRow:
    base: dict[str, Any] = {
        "day_brt": MATRIX_DAY,
        "mints": 140,
        "completed": 63,
        "rest_complete": 140,
        "curve_filled": 59,
        "graduated_board": 68,
        "pool_created": 68,
        "signals_1": 72,
        "signals_2": 9,
        "signals_3": 28,
        "signals_4": 31,
        "disagree_rest_filled": 81,
        "disagree_rest_board": 72,
        "disagree_rest_pool": 72,
        "disagree_filled_board": 37,
        "disagree_filled_pool": 37,
        "disagree_board_pool": 0,
        "rest_only_unclassified": 77,
    }
    base.update(overrides)
    return MemeGraduationMatrixRow(**base)


class FakeRestClient:
    """Duck-types ``PumpFunRestClient.get_mayhem_overview`` against the real
    captured fixture — never a hand-invented payload shape."""

    def __init__(self, metadata: dict[str, Any]) -> None:
        self._metadata = metadata

    async def get_mayhem_overview(self) -> NormalizedMayhemOverview:
        now = datetime(2026, 9, 12, 4, 22, tzinfo=UTC)
        return NormalizedMayhemOverview(metadata=self._metadata, observed_at=now, received_at=now)


class FakeRepository:
    def __init__(self, *, tracked: int) -> None:
        self._tracked = tracked

    async def token_coverage_count(self) -> int:
        return self._tracked

    async def created_counts_by_window(self, now: datetime) -> tuple[int, int]:
        del now
        return 3, 20

    async def mayhem_active_count(self) -> int:
        return 2

    async def graduations_last_24h(self, now: datetime) -> int:
        del now
        return 1

    async def graduation_matrix_for(self, now: datetime) -> MemeGraduationMatrixRow | None:
        del now
        return _matrix_row() if self._tracked else None


class TestDeriveState:
    def test_migrated_wins_over_completed(self) -> None:
        row = _row(
            completed_at=datetime(2026, 9, 12, 0, 30, tzinfo=UTC),
            migrated_at=datetime(2026, 9, 12, 1, 0, tzinfo=UTC),
        )
        assert derive_state(row) == "migrated"

    def test_completed_not_migrated(self) -> None:
        row = _row(completed_at=datetime(2026, 9, 12, 0, 30, tzinfo=UTC), migrated_at=None)
        assert derive_state(row) == "completed"

    def test_curve_when_neither_timestamp_set(self) -> None:
        """A token never observed completing/migrating is ``curve`` — the
        contract's nullable-timestamp design means "unknown" and "confirmed
        still bonding" share the same honest default, never a separate
        ambiguous boolean state."""
        assert derive_state(_row(completed_at=None, migrated_at=None)) == "curve"


class TestBuildTokenOut:
    def test_age_minutes_is_floor_division(self) -> None:
        row = _row(created_at=datetime(2026, 9, 12, 0, 0, tzinfo=UTC))
        now = datetime(2026, 9, 12, 0, 7, 30, tzinfo=UTC)
        out = build_token_out(row, now=now)
        assert out.age_minutes == 7

    def test_age_never_negative(self) -> None:
        """A clock skew that would make ``created_at`` look future never
        produces a negative age — floored at zero."""
        row = _row(created_at=datetime(2026, 9, 12, 1, 0, tzinfo=UTC))
        now = datetime(2026, 9, 12, 0, 0, tzinfo=UTC)
        out = build_token_out(row, now=now)
        assert out.age_minutes == 0

    def test_age_is_null_when_created_at_unknown(self) -> None:
        """Contract §1: a migration event can reach this radar before the
        token's own creation event does — ``created_at`` is then ``NULL``,
        and age must be ``None``, never ``0`` (0 would claim "just created")."""
        row = _row(created_at=None)
        out = build_token_out(row, now=datetime(2026, 9, 12, 0, 10, tzinfo=UTC))
        assert out.age_minutes is None
        assert out.created_at is None

    def test_carries_snapshot_source_and_observed_at(self) -> None:
        out = build_token_out(_row(), now=datetime(2026, 9, 12, 0, 10, tzinfo=UTC))
        assert out.snapshot_source == "pumpfun_rest"
        assert out.snapshot_observed_at is not None

    def test_no_features_row_yet_is_null_not_zero(self) -> None:
        """A mint recorded in ``meme_tokens`` with no ``meme_features_1m``
        row at all has no mcap/progress/snapshot fields — ``None``, never
        ``0`` (``repositories.meme._row_from_token_only``)."""
        row = _row(
            mcap_sol=None,
            curve_progress_pct=None,
            snapshot_observed_at=None,
            snapshot_source=None,
        )
        out = build_token_out(row, now=datetime(2026, 9, 12, 0, 1, tzinfo=UTC))
        assert out.mcap_sol is None
        assert out.curve_progress_pct is None
        assert out.snapshot_observed_at is None
        assert out.snapshot_source is None

    def test_carries_the_four_completion_signals_separately(self) -> None:
        """T4.2d: the four stamps travel as they are — the screen decides what
        a disagreement looks like; the API never folds them into one boolean."""
        t = datetime(2026, 9, 12, 5, 47, tzinfo=UTC)
        row = _row(
            rest_complete_seen_at=t,
            curve_filled_seen_at=None,
            graduated_board_seen_at=t.replace(minute=48),
            pool_created_at=t.replace(minute=46),
            pool_created_source="trenches_ws",
            completed_at=t.replace(minute=46),
            progress_denominator_source="global_params",
        )
        out = build_token_out(row, now=t)
        assert out.rest_complete_seen_at == t and out.curve_filled_seen_at is None
        assert out.graduated_board_seen_at == t.replace(minute=48)
        assert out.pool_created_at == t.replace(minute=46)
        assert out.pool_created_source == "trenches_ws"
        assert out.completed_at == t.replace(minute=46) and out.state == "completed"
        assert out.progress_denominator_source == "global_params"

    def test_an_unknown_denominator_is_said_not_left_null(self) -> None:
        out = build_token_out(_row(), now=datetime(2026, 9, 12, 0, 1, tzinfo=UTC))
        assert out.progress_denominator_source == "unknown"
        assert out.pool_created_source is None


class TestGraduationMatrix:
    def test_the_matrix_carries_the_counts_and_names_the_day(self) -> None:
        out = build_graduation_matrix_out(_matrix_row())
        assert out.day_brt == MATRIX_DAY and out.mints == 140 and out.completed == 63
        assert (out.rest_complete, out.curve_filled, out.graduated_board, out.pool_created) == (
            140,
            59,
            68,
            68,
        )
        assert (out.signals_1, out.signals_2, out.signals_3, out.signals_4) == (72, 9, 28, 31)
        assert out.disagree_rest_board == 72 and out.disagree_board_pool == 0
        assert out.rest_only_unclassified == 77
        assert out.disagreeing == 72 + 81 + 72 + 37 + 37 + 0, "the sum the strip turns amber on"


class TestBuildOverview:
    async def test_uses_meme_tokens_when_tracked(self) -> None:
        repo = FakeRepository(tracked=42)
        overview = await build_overview(
            cast(MemeRepository, repo), cast(PumpFunRestClient, FakeRestClient({}))
        )
        assert overview.source == "meme_tokens"
        assert overview.coins_created_24h == 3
        assert overview.coins_created_7d == 20
        assert overview.mayhem_active_coins == 2
        assert overview.graduations_24h == GraduationsOut(count=1, tracked_tokens=42)
        assert overview.coins_created_by_mode is None
        assert overview.graduation_matrix is not None
        assert overview.graduation_matrix.day_brt == MATRIX_DAY
        assert overview.graduation_matrix.rest_only_unclassified == 77

    async def test_falls_back_to_passthrough_when_no_coverage(self) -> None:
        raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
        repo = FakeRepository(tracked=0)
        overview = await build_overview(
            cast(MemeRepository, repo), cast(PumpFunRestClient, FakeRestClient(raw))
        )
        assert overview.source == "pumpfun_rest_mayhem_overview"
        assert overview.coins_created_24h == raw["coinsCreated"]["24h"]
        assert overview.coins_created_7d == raw["coinsCreated"]["7d"]
        assert overview.mayhem_active_coins == raw["activeCoins"]
        by_mode = overview.coins_created_by_mode
        assert by_mode is not None
        assert by_mode.auto.last_24h == raw["coinsCreatedByMode"]["auto"]["24h"]
        assert by_mode.manual.last_7d == raw["coinsCreatedByMode"]["manual"]["7d"]
        # No graduation count exists upstream -- honest null, tracked against
        # zero (this radar has not tracked any mint yet).
        assert overview.graduations_24h.count is None
        assert overview.graduations_24h.tracked_tokens == 0
        assert overview.graduations_24h.reason == "insufficient_coverage"
        assert overview.graduation_matrix is None, "no cohort of ours, no matrix"

    async def test_passthrough_observed_at_from_updated_at(self) -> None:
        raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
        repo = FakeRepository(tracked=0)
        overview = await build_overview(
            cast(MemeRepository, repo), cast(PumpFunRestClient, FakeRestClient(raw))
        )
        expected = datetime.fromtimestamp(raw["updatedAt"] / 1000, tz=UTC)
        assert overview.observed_at == expected
