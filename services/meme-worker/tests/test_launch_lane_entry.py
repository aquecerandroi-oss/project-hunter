"""``launch_lane_entry`` — one ``create`` frame -> a launch-lane proposal or a
named refusal (T4.67a), replaying a real PumpPortal capture (T4.1's own
fixture) for the frame shape and constructed edge cases for each refusal.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from hunter_exchanges.pumpfun import normalize
from hunter_exchanges.pumpfun.models import NormalizedMemeTokenCreated
from hunter_indicators.meme.curve import (
    INITIAL_REAL_TOKEN_RESERVES,
    INITIAL_VIRTUAL_TOKEN_RESERVES,
)
from hunter_meme_worker.launch_lane_entry import SERIES_LAUNCH, evaluate_create, features_of
from hunter_meme_worker.launch_lane_repo import LaunchRuleSpec
from hunter_meme_worker.launch_lane_symbols import RecentSymbols
from hunter_meme_worker.proposals import ProposalDraft

FIXTURES = Path(__file__).parents[3] / "packages/exchange-adapters/tests/fixtures/pumpfun"
NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)

SPEC = LaunchRuleSpec(
    id="01994d00-6c1a-7000-8000-000000000099",
    name="launch_v0",
    version="1",
    kind="research_only",
    exp_ref="EXP-M18",
    status="active",
    size_sol=Decimal("0.01"),
    max_creator_initial_sol=Decimal(2),
    exit_key="lancamento_6s_ou_primeiro_sell",
    time_stop_s=6,
    exit_on_first_third_party_sell=True,
    max_drawdown_from_peak_pct=Decimal(20),
)


def _real_create() -> NormalizedMemeTokenCreated:
    """A real ``pool == "pump"`` create frame from T4.1's own capture."""
    with (FIXTURES / "pumpportal_ws_capture_raw.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            raw = json.loads(line)
            if raw.get("txType") == "create" and raw.get("pool") == "pump":
                return normalize.parse_new_token(raw)
    raise AssertionError("no pump create frame in the fixture")


def _clean_event(
    *, creator_initial_sol: Decimal, creator_initial_tokens: Decimal
) -> NormalizedMemeTokenCreated:
    base = _real_create()
    return base.model_copy(
        update={
            "mint": "4k3Dyjzvzp8eYnbNBGVfL5V1Z6VpAmoEsFmPtnxJhMKZ",
            "symbol": "ZZZFRESH",
            "mayhem_enabled": False,
            "creator_initial_sol": creator_initial_sol,
            "creator_initial_tokens": creator_initial_tokens,
            # A standard curve's genesis virtual reserve minus this creator's
            # own buy — the exact identity
            # ``reconstruct_initial_real_token_reserves`` inverts (T4.45's own
            # live-verified check).
            "initial_virtual_token_reserves": INITIAL_VIRTUAL_TOKEN_RESERVES
            - creator_initial_tokens,
            "observed_at": NOW,
            "created_at": NOW,
        }
    )


def test_the_real_fixture_frame_parses_as_a_pump_create() -> None:
    event = _real_create()
    assert event.pool == "pump"
    assert event.mint


def test_features_of_reconstructs_the_denominator_from_a_real_frame() -> None:
    event = _real_create()
    features = features_of(event, recent_symbols=RecentSymbols())
    if event.creator_initial_tokens is None:
        assert features.initial_real_token_reserves is None
    else:
        assert features.initial_real_token_reserves is not None


def test_a_clean_create_drafts_one_proposal_per_active_launch_set() -> None:
    event = _clean_event(creator_initial_sol=Decimal("0.5"), creator_initial_tokens=Decimal(0))
    outcome = evaluate_create(event, [SPEC], recent_symbols=RecentSymbols(), now=NOW)
    assert len(outcome) == 1
    spec, result = outcome[0]
    assert spec is SPEC
    assert isinstance(result, ProposalDraft)
    assert result.mint == event.mint
    assert result.rule_set_id == SPEC.id
    assert result.status == "approved"
    assert result.decided_by == "rules"
    assert result.features_end_time == event.created_at
    assert result.reasons[0]["series"] == SERIES_LAUNCH
    assert result.reasons[0]["rule"] == "pista_de_lancamento/1"


def test_mayhem_refuses_by_name() -> None:
    event = _clean_event(
        creator_initial_sol=Decimal("0.5"), creator_initial_tokens=Decimal(0)
    ).model_copy(update={"mayhem_enabled": True})
    _, result = evaluate_create(event, [SPEC], recent_symbols=RecentSymbols(), now=NOW)[0]
    assert result == ("mayhem",)


def test_a_creator_buy_over_the_ceiling_refuses_by_name() -> None:
    event = _clean_event(creator_initial_sol=Decimal("3"), creator_initial_tokens=Decimal(0))
    _, result = evaluate_create(event, [SPEC], recent_symbols=RecentSymbols(), now=NOW)[0]
    assert result == ("creator_initial_sol_too_high",)


def test_an_insane_reconstruction_refuses_by_name() -> None:
    event = _clean_event(
        creator_initial_sol=Decimal("0.5"), creator_initial_tokens=Decimal(0)
    ).model_copy(update={"initial_virtual_token_reserves": Decimal(1)})
    _, result = evaluate_create(event, [SPEC], recent_symbols=RecentSymbols(), now=NOW)[0]
    assert result == ("initial_real_token_reserves_insane",)


def test_a_recent_symbol_clone_refuses_by_name() -> None:
    recent = RecentSymbols()
    recent.observe("ZZZFRESH", NOW)
    event = _clean_event(creator_initial_sol=Decimal("0.5"), creator_initial_tokens=Decimal(0))
    _, result = evaluate_create(event, [SPEC], recent_symbols=recent, now=NOW)[0]
    assert result == ("symbol_clone_recent",)


def test_the_reconstruction_matches_the_program_constant_on_the_clean_fixture() -> None:
    event = _clean_event(creator_initial_sol=Decimal("0.5"), creator_initial_tokens=Decimal(0))
    features = features_of(event, recent_symbols=RecentSymbols())
    assert features.initial_real_token_reserves == INITIAL_REAL_TOKEN_RESERVES
