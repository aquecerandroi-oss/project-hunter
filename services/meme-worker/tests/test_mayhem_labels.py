"""The site's ``mayhem_state = "enabled"`` (12/09/2026 after the upgrade) must
never reach ``meme_tokens`` — the CHECK knows only active/paused/completed/unknown
and the poll loop died on it (deploy 1033999, RestartCount 1). Unknown labels
become ``unknown`` at the rows boundary, logged once with the raw value."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from hunter_exchanges.pumpfun.models import NormalizedCurveState
from hunter_meme_worker import mayhem_labels
from hunter_meme_worker.curve_rows import snapshot_row, token_row_from_curve, tracked_from_curve
from hunter_meme_worker.mayhem_labels import known_mayhem_mode, known_mayhem_state

T0 = datetime(2026, 9, 12, 19, 39, 40, tzinfo=UTC)


def _state(*, mayhem_state: str | None, mayhem_mode: str | None = None) -> NormalizedCurveState:
    return NormalizedCurveState(
        mint="25xPUKHqporrJqzKgdShSuckPPPmTMdyVp5Ue256pump",
        virtual_sol_reserves=Decimal("30"),
        virtual_token_reserves=Decimal("1073000000"),
        real_sol_reserves=Decimal("0"),
        real_token_reserves=Decimal("793100000"),
        total_supply=Decimal("1000000000"),
        complete=False,
        market_cap_sol=Decimal("27.96"),
        source="pumpfun_rest",
        observed_at=T0,
        received_at=T0,
        mayhem_enabled=True,
        mayhem_state=mayhem_state,
        mayhem_mode=mayhem_mode,
    )


def test_known_labels_and_absence_pass_through_untouched() -> None:
    for label in ("active", "paused", "completed", "unknown", None):
        assert known_mayhem_state(label, mint="m", source="pumpfun_rest") == label
    for label in ("auto", "manual", "unknown", None):
        assert known_mayhem_mode(label, mint="m", source="pumpfun_rest") == label


def test_the_site_s_enabled_label_becomes_unknown_in_every_row() -> None:
    state = _state(mayhem_state="enabled", mayhem_mode="turbo")
    assert snapshot_row(state).mayhem_state == "unknown"
    assert snapshot_row(state).mayhem_mode == "unknown"
    assert token_row_from_curve(state).mayhem_state == "unknown"
    assert token_row_from_curve(state).mayhem_mode == "unknown"
    assert tracked_from_curve(state, None, None).mayhem_state == "unknown"


def test_the_raw_label_is_logged_once_per_mint_and_label(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[dict[str, object]] = []

    class _Logger:
        def warning(self, event: str, **kw: object) -> None:
            events.append({"event": event, **kw})

    monkeypatch.setattr(mayhem_labels, "logger", _Logger())
    monkeypatch.setattr(mayhem_labels, "_seen", set[tuple[str, str, str]]())
    for _ in range(3):
        assert known_mayhem_state("enabled", mint="m1", source="pumpfun_rest") == "unknown"
    assert known_mayhem_state("enabled", mint="m2", source="pumpfun_rest") == "unknown"
    assert [e["mint"] for e in events] == ["m1", "m2"]
    assert events[0] == {
        "event": "meme_mayhem_label_unknown",
        "field": "mayhem_state",
        "label": "enabled",
        "mint": "m1",
        "source": "pumpfun_rest",
    }
