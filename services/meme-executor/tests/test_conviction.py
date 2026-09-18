"""T4.61b — conviction sizing: the buy as a fraction of the cap, decided by the
evidence the admission already holds; never above the cap, never dust, and a
refusal (not a discount) on the one clean edge, ``entry_after_drop`` (KB-0118).

Every rung has a passing and a failing case; the floor, the two refusals, the
flag off (flat size as before, ladder written in shadow) and the engine seeing
the sized request as its ``requested`` cap are each proved. No network, no
database, no clock: the ladder is pure and the read is faked at its seam.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest

from hunter_meme_executor import conviction_read
from hunter_meme_executor.chain import CurveRead
from hunter_meme_executor.config import ExecutorConfig
from hunter_meme_executor.conviction import (
    ENV_CONVICTION_SIZING,
    REFUSAL_CONVICTION_TOO_LOW,
    REFUSAL_ENTRY_AFTER_DROP,
    ConvictionConfig,
    ConvictionEvidence,
    ConvictionLadder,
    evaluate_conviction,
)
from hunter_meme_executor.conviction_read import (
    apply_ladder,
    conviction_for,
    evidence_from,
    read_series_evidence,
)
from hunter_meme_executor.creator_flow import (
    CHAIN_FLOW_SOURCE,
    MEMORY_FLOW_SOURCE,
    TAPE_FLOW_SOURCE,
)
from hunter_meme_executor.heartbeat import policy_fields
from hunter_risk_meme import (
    MEME_PAPER_V0,
    CurveState,
    MemeContext,
    MemeEntryProposal,
    MemeKillSwitchInputs,
    MemeLimits,
    MemeWalletState,
    evaluate_meme_entry,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 18, 18, 5, tzinfo=UTC)  # 15:05 BRT
MINT = "5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump"
CAP = Decimal("0.28")
MIN_TRADE = Decimal("0.001")
ON = ConvictionConfig.from_env({ENV_CONVICTION_SIZING: "on"})
OFF = ConvictionConfig()


def evidence(**over: Any) -> ConvictionEvidence:
    """The full-conviction coin: chain-clean creator, 40 buyers, holders rising,
    shares under half the caps, real SOL at its 60 s peak."""
    base: dict[str, Any] = {
        "creator_decided_by": CHAIN_FLOW_SOURCE,
        "unique_buyers_60s": 40,
        "holders_rising": True,
        "evidence_as_of": NOW - timedelta(seconds=10),
        "bundled_share_pct": Decimal("0.05"),
        "top10_share_pct": Decimal("0.15"),
        "real_sol_now": Decimal("12.0"),
        "real_sol_peak": Decimal("12.0"),
        "peak_points": 4,
    }
    base.update(over)
    return ConvictionEvidence(**base)


def ladder(
    e: ConvictionEvidence, config: ConvictionConfig = ON, *, requested: Decimal = CAP
) -> ConvictionLadder:
    return evaluate_conviction(
        e, config, requested_sol=requested, max_sol_per_trade=CAP, min_trade_sol=MIN_TRADE
    )


def rung(lad: ConvictionLadder, name: str):
    return next(r for r in lad.rungs if r.name == name)


class TestTheConfig:
    def test_default_is_off_and_the_numbers_of_the_brief(self) -> None:
        c = ConvictionConfig.from_env({})
        assert c.enabled is False
        assert c.tape_only_multiplier == Decimal("0.5")
        assert c.min_unique_buyers == 25
        assert (c.buyers_multiplier, c.holders_multiplier) == (Decimal("0.5"), Decimal("0.5"))
        assert (c.bundled_max_pct, c.top10_max_pct) == (Decimal("0.10"), Decimal("0.20"))
        assert c.concentration_multiplier == Decimal("0.5")
        assert (c.drop_pct, c.drop_window_s) == (Decimal("0.50"), 60)
        assert c.floor == Decimal("0.25")
        assert c.evidence_max_age_s == 120

    def test_the_flag_reads_on_and_only_on(self) -> None:
        assert ConvictionConfig.from_env({ENV_CONVICTION_SIZING: "on"}).enabled is True
        assert ConvictionConfig.from_env({ENV_CONVICTION_SIZING: "1"}).enabled is True
        assert ConvictionConfig.from_env({ENV_CONVICTION_SIZING: "off"}).enabled is False
        assert ConvictionConfig.from_env({ENV_CONVICTION_SIZING: "maybe"}).enabled is False

    def test_overrides_in_range_apply_out_of_range_fall_back(self) -> None:
        c = ConvictionConfig.from_env(
            {
                "MEME_CONVICTION_TAPE_ONLY_MULT": "0.7",
                "MEME_CONVICTION_MIN_UNIQUE_BUYERS": "30",
                "MEME_CONVICTION_DROP_PCT": "0.35",
                "MEME_CONVICTION_DROP_WINDOW_S": "120",
                "MEME_CONVICTION_FLOOR": "0.5",
                "MEME_CONVICTION_BUYERS_MULT": "1.5",  # > 1 ⇒ default
                "MEME_CONVICTION_HOLDERS_MULT": "0",  # 0 ⇒ default (never a zero multiplier)
                "MEME_CONVICTION_BUNDLED_MAX_PCT": "abc",  # illegible ⇒ default
                "MEME_CONVICTION_EVIDENCE_MAX_AGE_S": "-5",  # below 1 ⇒ default
            }
        )
        assert c.tape_only_multiplier == Decimal("0.7")
        assert c.min_unique_buyers == 30
        assert c.drop_pct == Decimal("0.35")
        assert c.drop_window_s == 120
        assert c.floor == Decimal("0.5")
        assert c.buyers_multiplier == Decimal("0.5")
        assert c.holders_multiplier == Decimal("0.5")
        assert c.bundled_max_pct == Decimal("0.10")
        assert c.evidence_max_age_s == 120

    def test_the_executor_config_carries_it_and_the_heartbeat_publishes_it(self) -> None:
        assert ExecutorConfig.__dataclass_fields__["conviction"].default == ConvictionConfig()
        assert policy_fields(MEME_PAPER_V0)["conviction_sizing"] == "off"
        assert policy_fields(MEME_PAPER_V0, None, ON)["conviction_sizing"] == "on"


class TestEachRung:
    def test_full_conviction_is_the_cap(self) -> None:
        lad = ladder(evidence())
        assert lad.multiplier == Decimal(1)
        assert lad.sol_sized == CAP and lad.requested_sol == CAP
        assert lad.applied and lad.refusal is None
        assert [r.multiplier for r in lad.rungs] == [Decimal(1)] * 5

    def test_creator_tape_only_halves_chain_clean_keeps(self) -> None:
        assert rung(ladder(evidence(creator_decided_by=TAPE_FLOW_SOURCE)), "creator").reason == (
            "tape_only"
        )
        assert ladder(evidence(creator_decided_by=TAPE_FLOW_SOURCE)).multiplier == Decimal("0.5")
        assert ladder(evidence(creator_decided_by=CHAIN_FLOW_SOURCE)).multiplier == Decimal(1)

    def test_creator_unknown_or_remembered_seller_is_never_full_size(self) -> None:
        assert rung(ladder(evidence(creator_decided_by=None)), "creator").reason == "unknown"
        assert ladder(evidence(creator_decided_by=None)).multiplier == Decimal("0.5")
        memory = ladder(evidence(creator_decided_by=MEMORY_FLOW_SOURCE))
        assert rung(memory, "creator").reason == "not_chain_clean"
        assert memory.multiplier == Decimal("0.5")

    def test_buyers_below_25_halves_25_keeps_unknown_halves(self) -> None:
        assert ladder(evidence(unique_buyers_60s=24)).multiplier == Decimal("0.5")
        assert rung(ladder(evidence(unique_buyers_60s=24)), "buyers").reason == "below_min"
        assert ladder(evidence(unique_buyers_60s=25)).multiplier == Decimal(1)
        assert ladder(evidence(unique_buyers_60s=None)).multiplier == Decimal("0.5")
        assert rung(ladder(evidence(unique_buyers_60s=None)), "buyers").reason == "unknown"

    def test_holders_not_rising_halves_rising_keeps_unknown_halves(self) -> None:
        assert ladder(evidence(holders_rising=False)).multiplier == Decimal("0.5")
        assert rung(ladder(evidence(holders_rising=False)), "holders").reason == "not_rising"
        assert ladder(evidence(holders_rising=True)).multiplier == Decimal(1)
        assert ladder(evidence(holders_rising=None)).multiplier == Decimal("0.5")

    def test_concentration_above_half_the_caps_halves(self) -> None:
        assert ladder(evidence(bundled_share_pct=Decimal("0.11"))).multiplier == Decimal("0.5")
        assert ladder(evidence(top10_share_pct=Decimal("0.21"))).multiplier == Decimal("0.5")
        exact = ladder(evidence(bundled_share_pct=Decimal("0.10"), top10_share_pct=Decimal("0.20")))
        assert exact.multiplier == Decimal(1), "at the half-cap is within"
        assert ladder(evidence(bundled_share_pct=None)).multiplier == Decimal("0.5")
        assert rung(ladder(evidence(top10_share_pct=None)), "concentration").reason == "unknown"

    def test_a_50_pct_drop_from_the_60s_peak_refuses_not_discounts(self) -> None:
        """R56: soly 11,4 → 0,65, COVER 61,9 → 1,7, Punch 52,4 → 1,6 — the cell
        KB-0118 measured at −0,305 R. A half-sized bet there is still a bad bet."""
        lad = ladder(evidence(real_sol_now=Decimal("5.0"), real_sol_peak=Decimal("10.0")))
        assert lad.refusal == REFUSAL_ENTRY_AFTER_DROP
        assert lad.ladder_refusal == REFUSAL_ENTRY_AFTER_DROP
        assert lad.multiplier == Decimal(0) and lad.sol_sized == Decimal(0)
        assert not lad.applied
        assert rung(lad, "drop").reason == REFUSAL_ENTRY_AFTER_DROP
        assert "dd=0.5000" in rung(lad, "drop").value

    def test_a_drop_just_under_the_threshold_passes_and_a_rise_passes(self) -> None:
        under = ladder(evidence(real_sol_now=Decimal("5.01"), real_sol_peak=Decimal("10.0")))
        assert under.refusal is None and rung(under, "drop").multiplier == Decimal(1)
        rise = ladder(evidence(real_sol_now=Decimal("14.0"), real_sol_peak=Decimal("10.0")))
        assert rise.refusal is None and rung(rise, "drop").reason == "within_window"

    def test_no_peak_in_the_window_is_a_discount_never_a_pass_nor_a_refusal(self) -> None:
        none = ladder(evidence(real_sol_peak=None, peak_points=0))
        zero = ladder(evidence(real_sol_peak=Decimal(0), peak_points=1))
        for lad in (none, zero):
            assert lad.refusal is None
            assert rung(lad, "drop").reason == "peak_unknown"
            assert lad.multiplier == Decimal("0.5")

    def test_the_drop_refusal_beats_the_floor_refusal(self) -> None:
        lad = ladder(
            evidence(
                creator_decided_by=TAPE_FLOW_SOURCE,
                unique_buyers_60s=3,
                holders_rising=False,
                real_sol_now=Decimal("1"),
                real_sol_peak=Decimal("10"),
            )
        )
        assert lad.refusal == REFUSAL_ENTRY_AFTER_DROP


class TestTheFloorAndTheCap:
    def test_two_discounts_land_on_the_floor_and_are_sent(self) -> None:
        lad = ladder(evidence(creator_decided_by=TAPE_FLOW_SOURCE, unique_buyers_60s=10))
        assert lad.multiplier == Decimal("0.25")
        assert lad.refusal is None and lad.applied
        assert lad.sol_sized == Decimal("0.07")

    def test_three_discounts_are_refused_conviction_too_low(self) -> None:
        lad = ladder(
            evidence(
                creator_decided_by=TAPE_FLOW_SOURCE, unique_buyers_60s=10, holders_rising=False
            )
        )
        assert lad.multiplier == Decimal("0.125")
        assert lad.refusal == REFUSAL_CONVICTION_TOO_LOW
        assert not lad.applied

    def test_a_budget_below_min_trade_sol_is_refused_not_rounded_up(self) -> None:
        lad = evaluate_conviction(
            evidence(creator_decided_by=TAPE_FLOW_SOURCE),
            ON,
            requested_sol=Decimal("0.0015"),
            max_sol_per_trade=CAP,
            min_trade_sol=MIN_TRADE,
        )
        assert lad.sol_sized == Decimal("0.00075") < MIN_TRADE
        assert lad.refusal == REFUSAL_CONVICTION_TOO_LOW

    def test_never_above_the_cap_nor_above_the_proposal(self) -> None:
        assert ladder(evidence(), requested=Decimal("0.5")).sol_cap == CAP
        assert ladder(evidence(), requested=Decimal("0.1")).sol_cap == Decimal("0.1")
        halved = ladder(evidence(unique_buyers_60s=1), requested=Decimal("0.5"))
        assert halved.sol_sized == Decimal("0.14"), "half of the cap, not half of 0,5"

    def test_the_size_is_quantized_down_to_the_lamport(self) -> None:
        lad = evaluate_conviction(
            evidence(unique_buyers_60s=1),
            ON,
            requested_sol=Decimal("0.000000003"),
            max_sol_per_trade=CAP,
            min_trade_sol=Decimal("0.000000001"),
        )
        assert lad.sol_sized == Decimal("0.000000001")


class TestTheFlagOff:
    def test_off_is_the_flat_size_of_today_with_the_ladder_in_shadow(self) -> None:
        lad = ladder(
            evidence(
                creator_decided_by=TAPE_FLOW_SOURCE, unique_buyers_60s=10, holders_rising=False
            ),
            OFF,
        )
        assert lad.enabled is False and lad.applied is False
        assert lad.refusal is None, "off never refuses"
        assert lad.ladder_refusal == REFUSAL_CONVICTION_TOO_LOW, "but the row says what it would do"
        assert lad.requested_sol == CAP, "flat: min(cap, proposal) as today"
        assert lad.multiplier == Decimal("0.125")

    def test_off_never_refuses_entry_after_drop_either(self) -> None:
        lad = ladder(evidence(real_sol_now=Decimal("1"), real_sol_peak=Decimal("10")), OFF)
        assert lad.refusal is None and lad.requested_sol == CAP
        assert lad.ladder_refusal == REFUSAL_ENTRY_AFTER_DROP


class TestTheJson:
    def test_every_rung_and_the_totals_are_written(self) -> None:
        payload = ladder(evidence(unique_buyers_60s=20)).as_json()
        assert payload["enabled"] is True and payload["applied"] is True
        assert payload["multiplier"] == "0.5"
        assert (payload["sol_cap"], payload["sol_sized"]) == ("0.280000000", "0.140000000")
        assert payload["sol_requested"] == "0.140000000"
        assert payload["refusal"] == "" and payload["ladder_refusal"] == ""
        names = [r["name"] for r in payload["rungs"]]
        assert names == ["creator", "buyers", "holders", "concentration", "drop"]
        buyers = payload["rungs"][1]
        assert buyers == {
            "name": "buyers",
            "value": "20",
            "multiplier": "0.5",
            "reason": "below_min",
        }
        assert set(ConvictionConfig().as_json()) >= {"enabled", "floor", "drop_pct"}


# --- the engine sees the sized request as its ``requested`` cap ---------------

AS_OF = NOW
INITIAL_REAL = 793_100_000_000_000


def _engine_inputs() -> tuple[MemeWalletState, MemeLimits, CurveState, MemeContext]:
    wallet = MemeWalletState(
        wallet_id="w1",
        as_of=AS_OF,
        sol_balance=Decimal("0.73"),
        day_start_sol_equity=Decimal("0.73"),
        peak_sol_equity=Decimal("0.73"),
        day_start_utc=datetime(2026, 9, 18, 3, 0, tzinfo=UTC),  # 00:00 BRT
    )
    limits = MEME_PAPER_V0.model_validate(
        {
            **MEME_PAPER_V0.model_dump(),
            "max_sol_per_trade": CAP,
            "max_exposure_per_mint_sol": CAP,
            "wallet_max_sol": Decimal("0.75"),
            "daily_loss_cap_sol": Decimal("0.30"),
        }
    )
    curve = CurveState(
        mint=MINT,
        # 30 SOL real on the curve: the 0,5 % impact ceiling (0,30 SOL) sits
        # above the 0,28 cap, so the ladder's request is what binds.
        virtual_sol_reserves=60_000_000_000,
        virtual_token_reserves=900_000_000_000_000,
        real_sol_reserves=30_000_000_000,
        real_token_reserves=INITIAL_REAL * 8 // 10,
        total_supply=1_000_000_000_000_000,
        complete=False,
        creator="AsRQHoHxfBYqvxJZxK9RtJUnRZcCwUoh9KNpVxH6Jhnd",
        is_mayhem_mode=False,
        slot=447_900_000,
        commitment="confirmed",
        observed_at=AS_OF - timedelta(seconds=2),
        source="solana_rpc",
    )
    context = MemeContext(
        mint=MINT,
        token_created_at=AS_OF - timedelta(seconds=120),
        token_age_source="meme_tokens.created_at",
        initial_real_token_reserves=INITIAL_REAL,
        organic_volume_1m_sol=Decimal("40"),
        volume_ts=AS_OF - timedelta(seconds=30),
        volume_window_complete=True,
        bundled_share_pct=Decimal("0.05"),
        top10_share_pct=Decimal("0.15"),
        holder_denominator_valid=True,
        creator_net_sol=Decimal("1"),
    )
    return wallet, limits, curve, context


def _proposal(requested: Decimal = CAP) -> MemeEntryProposal:
    return MemeEntryProposal(
        proposal_id="p1",
        wallet_id="w1",
        mint=MINT,
        requested_sol=requested,
        max_slippage_pct=Decimal("0.01"),
        priority_fee_sol=Decimal("0.0001"),
        mode="paper",
    )


class TestTheEngineSizesFromTheLadder:
    def test_apply_ladder_hands_the_engine_the_sized_request(self) -> None:
        lad = ladder(evidence(unique_buyers_60s=10))
        sized = apply_ladder(_proposal(), lad)
        assert sized.requested_sol == Decimal("0.14")
        assert sized.proposal_id == "p1" and sized.mint == MINT
        assert apply_ladder(_proposal(), ladder(evidence(), OFF)).requested_sol == CAP
        refused = ladder(evidence(real_sol_now=Decimal(1), real_sol_peak=Decimal(10)))
        assert apply_ladder(_proposal(), refused).requested_sol == CAP, "engine still judges"

    def test_sizing_and_check_23_use_the_final_size(self) -> None:
        wallet, limits, curve, context = _engine_inputs()
        lad = ladder(evidence(unique_buyers_60s=10))
        decision = evaluate_meme_entry(
            apply_ladder(_proposal(), lad),
            wallet,
            limits,
            curve,
            context,
            MemeKillSwitchInputs(),
            live_enabled=False,
            curve_fee_pct=Decimal("0.0125"),
            creates_ata=True,
        )
        assert decision.approved, decision.refusals
        assert decision.sizing is not None
        assert decision.sizing.sol_final == Decimal("0.14")
        assert decision.sizing.binding_constraint == "requested"
        assert decision.sizing.requested_sol == Decimal("0.14")
        sizing_check = next(c for c in decision.checks if c.name == "sizing")
        assert sizing_check.value == Decimal("0.14") and sizing_check.passed
        assert decision.sizing.max_sol_cost_sol == Decimal("0.1414")

    def test_flat_when_off_is_the_cap(self) -> None:
        wallet, limits, curve, context = _engine_inputs()
        decision = evaluate_meme_entry(
            apply_ladder(_proposal(), ladder(evidence(unique_buyers_60s=10), OFF)),
            wallet,
            limits,
            curve,
            context,
            MemeKillSwitchInputs(),
            live_enabled=False,
            curve_fee_pct=Decimal("0.0125"),
            creates_ata=True,
        )
        assert decision.approved and decision.sizing is not None
        assert decision.sizing.sol_final == CAP


# --- the read: one bounded statement, faked at the seam ------------------------


class FakeResult:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    def mappings(self) -> FakeResult:
        return self

    def first(self) -> dict[str, Any] | None:
        return self._row


class FakeSession:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self.row = row
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, statement: Any, params: dict[str, Any]) -> FakeResult:
        self.calls.append((str(statement), params))
        return FakeResult(self.row)


@dataclass
class FakeConfig:
    conviction: ConvictionConfig = ON


@dataclass
class FakeCtx:
    config: FakeConfig = field(default_factory=FakeConfig)
    session_factory: Any = None


@dataclass
class FakeAccount:
    real_sol_reserves: int = 6_400_000_000


@dataclass
class FakeCurveRead:
    account: FakeAccount = field(default_factory=FakeAccount)


@dataclass
class FakeBuilt:
    context: MemeContext
    extras: dict[str, Any]


def _built(decided_by: str = CHAIN_FLOW_SOURCE) -> FakeBuilt:
    return FakeBuilt(
        context=_engine_inputs()[3], extras={"creator_verdict": {"decided_by": decided_by}}
    )


class TestTheRead:
    @pytest.mark.asyncio
    async def test_one_statement_two_windows(self) -> None:
        session = FakeSession(
            {
                "peak_real_sol": Decimal("12.5"),
                "peak_points": 4,
                "as_of": NOW - timedelta(seconds=8),
                "unique_buyers_60s": 31,
                "holders_rising": True,
            }
        )
        series = await read_series_evidence(cast(Any, session), MINT, config=ON, now=NOW)
        assert len(session.calls) == 1
        sql, params = session.calls[0]
        assert "meme_curve_snapshots" in sql and "meme_features_15s" in sql
        assert params["peak_since"] == NOW - timedelta(seconds=60)
        assert params["fresh_since"] == NOW - timedelta(seconds=120)
        assert params["now"] == NOW and params["mint"] == MINT
        assert series["unique_buyers_60s"] == 31

    @pytest.mark.asyncio
    async def test_no_row_is_an_empty_series(self) -> None:
        series = await read_series_evidence(cast(Any, FakeSession(None)), MINT, config=ON, now=NOW)
        assert series == {}

    def test_evidence_from_the_admission_and_the_series(self) -> None:
        series = {
            "peak_real_sol": Decimal("12.8"),
            "peak_points": 3,
            "as_of": NOW - timedelta(seconds=8),
            "unique_buyers_60s": 31,
            "holders_rising": False,
        }
        e = evidence_from(cast(Any, _built(TAPE_FLOW_SOURCE)), cast(Any, FakeCurveRead()), series)
        assert e.creator_decided_by == TAPE_FLOW_SOURCE
        assert e.unique_buyers_60s == 31 and e.holders_rising is False
        assert e.real_sol_now == Decimal("6.4")
        assert e.real_sol_peak == Decimal("12.8") and e.peak_points == 3
        assert e.bundled_share_pct == Decimal("0.05") and e.top10_share_pct == Decimal("0.15")
        # 6,4 against a 12,8 peak is exactly the 50 % drop.
        assert ladder(e).refusal == REFUSAL_ENTRY_AFTER_DROP

    def test_evidence_with_nothing_measured_is_all_none(self) -> None:
        e = evidence_from(
            cast(Any, FakeBuilt(_engine_inputs()[3], {})), cast(Any, FakeCurveRead()), {}
        )
        assert e.creator_decided_by is None and e.unique_buyers_60s is None
        assert e.holders_rising is None and e.real_sol_peak is None and e.peak_points == 0
        assert ladder(e).refusal == REFUSAL_CONVICTION_TOO_LOW, "four unknowns: 1/16 < floor"

    @pytest.mark.asyncio
    async def test_conviction_for_reads_once_and_judges(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session = FakeSession(
            {
                "peak_real_sol": Decimal("6.4"),
                "peak_points": 2,
                "as_of": NOW - timedelta(seconds=8),
                "unique_buyers_60s": 40,
                "holders_rising": True,
            }
        )

        @asynccontextmanager
        async def fake_role_session(*args: Any, **kwargs: Any) -> AsyncGenerator[FakeSession]:
            yield session

        monkeypatch.setattr(conviction_read, "role_session", fake_role_session)
        limits = _engine_inputs()[1]
        lad = await conviction_for(
            cast(Any, FakeCtx()),
            cast(Any, _built()),
            cast(CurveRead, FakeCurveRead()),
            proposal=_proposal(Decimal("0.5")),
            limits=limits,
            now=NOW,
        )
        assert len(session.calls) == 1
        assert lad.applied and lad.sol_sized == CAP and lad.multiplier == Decimal(1)
