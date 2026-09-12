"""T4.5 — the replay of one mint's snapshot series through the paper wallet.

The canonical synthetic series keeps ``k = 9000`` at every point (each snapshot
is a legitimate point on the same curve, as if other traders had moved it) and is
built so the fill lands on a **different** point from the one that decided:

| # | when     | reserves      | real | progress | what happens                  |
|---|----------|---------------|------|----------|-------------------------------|
| 0 | T0+120 s | 30,0 / 300    | 200  | 16,67 %  | the gate allows (the intent)  |
| 1 | T0+150 s | 32,0 / 281,25 | 181,25 | 24,48 % | **the buy fills here**       |
| 2 | T0+210 s | 60,0 / 150    | 50   | 79,17 %  | mark 1,3405 → 3x target hit   |
| 3 | T0+240 s | 60,0 / 150    | 50   | 79,17 %  | **the sell fills here**       |

Hand arithmetic for the numbers asserted below, with 0,405 SOL of size (which at
1,25 % puts exactly 0,400 SOL into the curve), no priority fee:

- tokens at snapshot 1: ``281,25 * 0,4 / 32,4 = 125/36 = 3,4722...``;
- mark at snapshot 2: ``60q/(150+q) = 300/221`` gross, ``296,25/221 = 1,340497...``
  net of the sell fee;
- PnL ``1,340497... - 0,405 = 0,935497...`` SOL, initial risk ``0,405`` SOL (the
  whole cost: ``docs/RISK_ENGINE_MEME.md`` §5), so ``R = 2,309870...``.

Note what snapshot 1 does to the entry: at the decision point 0,4 SOL would have
bought ``3,947...`` tokens, and by the time the fill is priced it buys
``3,472...`` — 12 % fewer. That is the concurrency slippage this task exists to
measure, and it is the reason a fill is never priced at the state that produced
the intent.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from hunter_indicators.meme.curve import CurveReserves, tokens_for_sol
from hunter_indicators.meme.models import PaperWalletLimits
from hunter_indicators.meme.replay import (
    CurveSnapshot,
    MintOutcome,
    MintSeries,
    ReplayPlan,
    SkippedMint,
    replay_mint,
    replay_mints,
    snapshot_from_mapping,
)
from hunter_indicators.meme.rules import EntryGate, ExitRules

REPO = Path(__file__).resolve().parents[4]
FIXTURES = (
    Path(__file__).resolve().parents[3] / "exchange-adapters" / "tests" / "fixtures" / "pumpfun"
)
T0 = datetime(2026, 9, 12, 4, 0, 0, tzinfo=UTC)
MINT = "SYNTH1111111111111111111111111111111111111"
SIZE = Decimal("0.405")

GATE = EntryGate(
    key="teste_porta",
    version=1,
    description="Test fixture: age 60-900 s, progress 1-20 %, participation <= 5 %.",
    min_age_s=60,
    max_age_s=900,
    min_progress_pct=Decimal(1),
    max_progress_pct=Decimal(20),
    max_participation_pct=Decimal(5),
)
EXITS = ExitRules(
    key="teste_saida",
    version=1,
    description="Test fixture: 3x target, 40 % trailing, 30 min time stop, 50 % loss floor.",
    target_multiple=Decimal(3),
    trailing_drawdown_pct=Decimal(40),
    time_stop_s=1800,
    max_loss_pct=Decimal(50),
)
LIMITS = PaperWalletLimits(
    max_balance_sol=Decimal(5),
    max_sol_per_trade=Decimal(1),
    daily_loss_cap_sol=Decimal(2),
    max_open_positions=3,
    max_exposure_per_mint_sol=Decimal(1),
    fee_pct=Decimal("1.25"),
    fill_delay_snapshots=1,
)
PLAN = ReplayPlan(
    gate=GATE,
    exits=EXITS,
    limits=LIMITS,
    size_sol=SIZE,
    priority_fee_sol=Decimal(0),
    opening_balance_sol=Decimal(5),
)


def _snapshot(
    offset_s: int,
    sol: str,
    tokens: str,
    real: str,
    *,
    mint: str = MINT,
    volume: Decimal | None = Decimal(10),
    creator_net_seller: bool | None = False,
    rug: bool | None = False,
    migrated: bool = False,
    complete: bool = False,
) -> CurveSnapshot:
    return CurveSnapshot(
        mint=mint,
        observed_at=T0 + timedelta(seconds=offset_s),
        reserves=CurveReserves(
            Decimal(sol),
            Decimal(tokens),
            real_token_reserves=Decimal(real),
            initial_real_token_reserves=Decimal(240),
            complete=complete,
        ),
        curve_volume_1m_sol=volume,
        creator_net_seller=creator_net_seller,
        rug_suspected=rug,
        migrated=migrated,
    )


CANONICAL = MintSeries(
    mint=MINT,
    created_at=T0,
    snapshots=(
        _snapshot(120, "30", "300", "200"),
        _snapshot(150, "32", "281.25", "181.25"),
        _snapshot(210, "60", "150", "50"),
        _snapshot(240, "60", "150", "50"),
    ),
)


def _outcome(series: MintSeries = CANONICAL, plan: ReplayPlan = PLAN) -> MintOutcome:
    result = replay_mint(series, plan)
    assert isinstance(result, MintOutcome), result
    return result


def test_the_replay_produces_the_labs_outcome_shape_with_the_hand_checked_numbers() -> None:
    outcome = _outcome()
    assert outcome.mint == MINT
    assert outcome.day == "2026-09-12"
    assert outcome.decision_index == 0
    assert outcome.entry_index == 1
    assert outcome.entry_ts == T0 + timedelta(seconds=150)
    assert outcome.entry_size_sol == Decimal("0.405")
    assert outcome.tokens == Decimal("112.5") / Decimal("32.4")
    assert outcome.exit_index == 3
    assert outcome.exit_ts == T0 + timedelta(seconds=240)
    assert outcome.exit_reason == "target_multiple"
    assert outcome.closed
    assert outcome.holding_s == 90
    # RISK_ENGINE_MEME §5: on a curve the risk is everything paid, not a stop distance.
    assert outcome.initial_risk_sol == Decimal("0.405") == outcome.entry_size_sol
    assert outcome.exit_proceeds_sol is not None
    assert abs(outcome.exit_proceeds_sol - Decimal("1.3404977376")) < Decimal("1e-9")
    assert abs(outcome.pnl_sol - Decimal("0.9354977376")) < Decimal("1e-9")
    assert abs(outcome.r_multiple - Decimal("2.3098709")) < Decimal("1e-7")
    assert outcome.unknown == ()


def test_the_fill_is_priced_at_the_next_snapshot_not_the_one_that_decided() -> None:
    outcome = _outcome()
    at_decision = tokens_for_sol(CANONICAL.snapshots[0].reserves, Decimal("0.4"))
    at_fill = tokens_for_sol(CANONICAL.snapshots[1].reserves, Decimal("0.4"))
    assert at_fill < at_decision  # the curve moved against us between the two
    assert outcome.tokens == at_fill
    assert outcome.slippage_tokens == at_decision - at_fill


def test_a_snapshot_after_the_decision_cannot_change_the_entry() -> None:
    """The leakage test: the future is rewritten and the entry does not move."""
    rewritten = MintSeries(
        mint=MINT,
        created_at=T0,
        snapshots=(
            CANONICAL.snapshots[0],
            CANONICAL.snapshots[1],
            _snapshot(210, "300", "30", "0"),  # an absurd pump
            _snapshot(240, "300", "30", "0"),
        ),
    )
    before, after = _outcome(), _outcome(rewritten)
    assert (before.decision_index, before.entry_index) == (after.decision_index, after.entry_index)
    assert before.tokens == after.tokens
    assert before.entry_size_sol == after.entry_size_sol
    assert after.pnl_sol > before.pnl_sol  # only the exit changed, as it must


def test_the_only_way_to_fill_at_the_decision_state_is_to_bypass_the_replay() -> None:
    """The cheat is representable and it is refused, by name, at the wallet."""
    from hunter_indicators.meme.paper import PaperCurveWallet

    wallet = PaperCurveWallet(limits=LIMITS, balance_sol=Decimal(5), opened_at=T0)
    decision = CANONICAL.snapshots[0]
    cheat = wallet.buy(
        MINT,
        SIZE,
        decision.reserves,
        ts=decision.observed_at,
        intent_ts=decision.observed_at,
    )
    assert not cheat.accepted
    assert cheat.reason == "fill_not_after_intent"
    with pytest.raises(ValueError, match="fill_delay_snapshots"):
        PaperWalletLimits(
            max_balance_sol=Decimal(5),
            max_sol_per_trade=Decimal(1),
            daily_loss_cap_sol=Decimal(2),
            max_open_positions=3,
            max_exposure_per_mint_sol=Decimal(1),
            fee_pct=Decimal("1.25"),
            fill_delay_snapshots=0,
        )


def test_a_series_that_ends_before_the_fill_is_skipped_by_name() -> None:
    one = MintSeries(mint=MINT, created_at=T0, snapshots=(CANONICAL.snapshots[0],))
    result = replay_mint(one, PLAN)
    assert isinstance(result, SkippedMint)
    assert result.reason == "no_fill_snapshot"
    assert result.refusals == ("no_fill_snapshot",)


def test_a_gate_that_never_opens_reports_every_refusal_it_collected() -> None:
    late = MintSeries(
        mint=MINT,
        created_at=T0,
        snapshots=(_snapshot(120, "60", "150", "50"), _snapshot(150, "60", "150", "50")),
    )
    result = replay_mint(late, PLAN)
    assert isinstance(result, SkippedMint)
    assert result.reason == "never_allowed"
    assert result.refusals == ("progress_above_max",)


def test_an_exit_that_cannot_be_filled_is_censored_not_invented() -> None:
    truncated = MintSeries(mint=MINT, created_at=T0, snapshots=CANONICAL.snapshots[:3])
    outcome = _outcome(truncated)
    assert not outcome.closed
    assert outcome.exit_reason == "open_at_series_end"
    assert outcome.unfilled_exit_reason == "target_multiple"
    assert outcome.exit_proceeds_sol is None
    assert outcome.mark_at_exit_sol is not None
    assert outcome.pnl_sol == outcome.mark_at_exit_sol - outcome.entry_size_sol


def test_the_time_stop_closes_a_position_that_never_moved() -> None:
    flat = MintSeries(
        mint=MINT,
        created_at=T0,
        snapshots=tuple(_snapshot(offset, "30", "300", "200") for offset in (120, 150, 1960, 1990)),
    )
    outcome = _outcome(flat)
    assert outcome.exit_reason == "time_stop"
    assert outcome.holding_s == 1840
    assert outcome.pnl_sol < 0  # two fees and the curve impact, nothing else happened


def test_an_unknown_rug_signal_travels_into_the_outcome() -> None:
    blind = MintSeries(
        mint=MINT,
        created_at=T0,
        snapshots=tuple(
            CurveSnapshot(
                mint=snapshot.mint,
                observed_at=snapshot.observed_at,
                reserves=snapshot.reserves,
                curve_volume_1m_sol=snapshot.curve_volume_1m_sol,
                creator_net_seller=snapshot.creator_net_seller,
                rug_suspected=None,
                migrated=snapshot.migrated,
            )
            for snapshot in CANONICAL.snapshots
        ),
    )
    assert _outcome(blind).unknown == ("rug_signal_unknown",)


def test_many_mints_share_one_wallet_and_the_day_blocks_feed_the_lab() -> None:
    second = MintSeries(
        mint="SYNTH2222222222222222222222222222222222222",
        created_at=T0 + timedelta(days=1),
        snapshots=tuple(
            _snapshot(
                86400 + offset,
                sol,
                tokens,
                real,
                mint="SYNTH2222222222222222222222222222222222222",
            )
            for offset, sol, tokens, real in (
                (120, "30", "300", "200"),
                (150, "32", "281.25", "181.25"),
                (1960, "30", "300", "200"),
                (1990, "30", "300", "200"),
            )
        ),
    )
    result = replay_mints([CANONICAL, second], PLAN, opened_at=T0)
    assert [o.mint for o in result.outcomes] == [MINT, second.mint]
    assert result.skipped == ()
    days, values = result.day_blocks("r_multiple")
    assert days == ["2026-09-12", "2026-09-13"]
    assert len(values) == 2
    assert values[0] > 0 > values[1]
    pnl_days, pnl_values = result.day_blocks("pnl_sol")
    assert pnl_days == days
    assert sum(pnl_values) == pytest.approx(float(result.total_pnl_sol))
    assert result.ledger[0].kind == "open"


def test_the_day_blocks_are_exactly_what_the_block_ci_bootstrap_consumes() -> None:
    """Smoke against the real ``blocos90.py`` the Lab uses (skipped if absent)."""
    path = REPO / ".claude" / "state" / "exp-drafts" / "t362b" / "blocos90.py"
    if not path.exists():
        pytest.skip("blocos90.py is a research script; not present in this checkout")
    spec = importlib.util.spec_from_file_location("blocos90_t45", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations through sys.modules
    try:
        spec.loader.exec_module(module)
    finally:
        del sys.modules[spec.name]
    result = replay_mints([CANONICAL], PLAN, opened_at=T0)
    days, values = result.day_blocks("r_multiple")
    interval = module.ic_media(days, values, reamostragens=200, seed=20260912)
    assert interval.n == 1
    assert interval.dias == 1


def test_the_package_never_reads_a_clock_and_never_touches_io() -> None:
    forbidden = ("datetime.now", "utcnow", "time.time", "open(", "sqlalchemy", "httpx", "redis")
    for module in sorted(
        (REPO / "packages" / "indicators" / "hunter_indicators" / "meme").glob("*.py")
    ):
        source = module.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{module.name} mentions {token}"


def test_a_snapshot_can_be_built_from_a_plain_mapping_of_a_real_capture() -> None:
    coin = json.loads((FIXTURES / "coin_a41_raw.json").read_text(encoding="utf-8"))
    snapshot = snapshot_from_mapping(
        {
            "mint": coin["mint"],
            "observed_at": T0,
            "virtual_sol_reserves": Decimal(coin["virtual_sol_reserves"]) / Decimal(10**9),
            "virtual_token_reserves": Decimal(coin["virtual_token_reserves"]) / Decimal(10**6),
            "real_token_reserves": Decimal(coin["real_token_reserves"]) / Decimal(10**6),
            "complete": coin["complete"],
        }
    )
    assert snapshot.mint == coin["mint"]
    assert snapshot.reserves.initial_real_token_reserves is None
    assert snapshot.curve_volume_1m_sol is None
    assert snapshot.creator_net_seller is None
    assert snapshot.rug_suspected is None


def test_the_real_capture_of_a_launch_cannot_be_traded_and_says_why() -> None:
    """Seven live create events: the gate refuses all seven, and names the missing input.

    The WS create event carries the virtual reserves but not
    ``initial_real_token_reserves``, so curve progress is **unmeasurable** from
    this capture alone — the gate says ``progress_unknown`` instead of treating a
    fresh launch as 0 % progress. This is the whole T4.5 discipline on real bytes:
    today's free feed cannot answer the entry question, and the code says so.
    """
    rows = json.loads((FIXTURES / "pumpportal_ws_a41_live.json").read_text(encoding="utf-8"))
    series: list[MintSeries] = []
    for row in rows:
        payload = json.loads(str(row["raw"]))
        if "vTokensInBondingCurve" not in payload:
            continue
        observed_at = datetime.fromisoformat(str(row["observed_at"]))
        series.append(
            MintSeries(
                mint=str(payload["mint"]),
                created_at=observed_at,
                snapshots=(
                    snapshot_from_mapping(
                        {
                            "mint": str(payload["mint"]),
                            "observed_at": observed_at + timedelta(seconds=120),
                            "virtual_sol_reserves": Decimal(str(payload["vSolInBondingCurve"])),
                            "virtual_token_reserves": Decimal(
                                str(payload["vTokensInBondingCurve"])
                            ),
                        }
                    ),
                ),
            )
        )
    assert len(series) == 7
    result = replay_mints(series, PLAN, opened_at=T0)
    assert result.outcomes == ()
    assert len(result.skipped) == 7
    assert {s.reason for s in result.skipped} == {"never_allowed"}
    assert {s.refusals for s in result.skipped} == {
        ("progress_unknown", "creator_net_seller_unknown", "curve_volume_1m_unknown")
    }
