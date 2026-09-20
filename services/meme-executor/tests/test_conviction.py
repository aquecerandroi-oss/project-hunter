"""T4.61b/T4.61c — conviction sizing: the buy as a fraction of the cap, decided by
the evidence the admission already holds; never above the cap, never dust, and a
refusal (not a discount) on the one clean edge, ``entry_after_drop`` (KB-0118) —
and, since T4.61c, on the edge that cannot be seen (``entry_after_drop_unknown``).

Every rung has a passing and a failing case; the two refusals of the ladder, the
floor, the engine binding by the ladder's own name (A4), the refusal as
``approved = false`` with ``first_refusal`` (A9), dust refused against the live
floor (A5), the guarded read (A1: exception and timeout with the flag on, no read
with it off) and the 30 s cooldown of ``entry_after_drop`` are each proved. No
network, no database, no clock: the ladder is pure and the read is faked at its seam.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest

from hunter_indicators.meme.drawdown import ReservePoint
from hunter_meme_executor import conviction_read
from hunter_meme_executor.chain import CurveRead
from hunter_meme_executor.config import ExecutorConfig
from hunter_meme_executor.conviction import (
    ENV_CONVICTION_SIZING,
    LADDER_OFF,
    REFUSAL_CONVICTION_TOO_LOW,
    REFUSAL_ENTRY_AFTER_DROP,
    REFUSAL_ENTRY_AFTER_DROP_UNKNOWN,
    ConvictionConfig,
    ConvictionEvidence,
    ConvictionLadder,
    evaluate_conviction,
)
from hunter_meme_executor.conviction_read import (
    ConvictionOutcome,
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
from hunter_meme_executor.refusal_cooldown import (
    DETERMINISTIC_REFUSALS,
    SHORT_COOLDOWNS,
    cooling_mints_by_window,
)
from hunter_risk_meme import (
    MEME_PAPER_V0,
    REFUSAL_NAMES,
    CurveState,
    MemeContext,
    MemeConviction,
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
ON = ConvictionConfig.from_env({ENV_CONVICTION_SIZING: "on"})


def photos(*pairs: tuple[int, str]) -> tuple[ReservePoint, ...]:
    """``(seconds before NOW, real SOL)`` stored photos, received when observed."""
    return tuple(
        ReservePoint(
            observed_at=NOW - timedelta(seconds=ago),
            received_at=NOW - timedelta(seconds=ago),
            real_sol=Decimal(sol),
        )
        for ago, sol in pairs
    )


FLAT = photos((40, "12.0"), (25, "12.0"), (10, "12.0"))


def evidence(**over: Any) -> ConvictionEvidence:
    """The full-conviction coin: chain-clean creator, 40 buyers, holders rising,
    shares under half the caps, real SOL at its 60 s peak with three photos."""
    base: dict[str, Any] = {
        "creator_decided_by": CHAIN_FLOW_SOURCE,
        "unique_buyers_60s": 40,
        "holders_rising": True,
        "evidence_as_of": NOW - timedelta(seconds=10),
        "bundled_share_pct": Decimal("0.05"),
        "top10_share_pct": Decimal("0.15"),
        "real_sol_now": Decimal("12.0"),
        "curve_points": FLAT,
    }
    base.update(over)
    return ConvictionEvidence(**base)


def ladder(
    e: ConvictionEvidence, config: ConvictionConfig = ON, *, requested: Decimal = CAP
) -> ConvictionLadder:
    return evaluate_conviction(e, config, requested_sol=requested, max_sol_per_trade=CAP, as_of=NOW)


def rung(lad: ConvictionLadder, name: str):
    return next(r for r in lad.rungs if r.name == name)


def dropped(now: str = "5.0", *pairs: tuple[int, str]) -> ConvictionEvidence:
    """Two photos at the peak, the admission's read after the fall."""
    return evidence(
        real_sol_now=Decimal(now), curve_points=photos(*(pairs or ((30, "10.0"), (20, "9.5"))))
    )


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
        assert not hasattr(c, "peak_unknown_multiplier"), "T4.61c: unknown refuses, no discount"

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
                "MEME_CONVICTION_PEAK_UNKNOWN_MULT": "0.9",  # removed in T4.61c: ignored
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
        assert lad.sol_sized == CAP and lad.refusal is None
        assert [r.multiplier for r in lad.rungs] == [Decimal(1)] * 5
        assert rung(lad, "drop").reason == "within_window"

    def test_creator_tape_only_halves_chain_clean_keeps(self) -> None:
        tape = ladder(evidence(creator_decided_by=TAPE_FLOW_SOURCE))
        assert rung(tape, "creator").reason == "tape_only" and tape.multiplier == Decimal("0.5")
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
        lad = ladder(dropped("5.0"))
        assert lad.refusal == REFUSAL_ENTRY_AFTER_DROP
        assert lad.multiplier == Decimal(0) and lad.sol_sized == Decimal(0)
        assert rung(lad, "drop").reason == REFUSAL_ENTRY_AFTER_DROP
        assert "dd=0.500000" in rung(lad, "drop").value and "peak=10.0" in rung(lad, "drop").value

    def test_a_drop_just_under_the_threshold_passes_and_a_rise_passes(self) -> None:
        under = ladder(dropped("5.01"))
        assert under.refusal is None and rung(under, "drop").multiplier == Decimal(1)
        rise = ladder(dropped("14.0"))
        assert rise.refusal is None and rung(rise, "drop").reason == "within_window"

    def test_the_peak_is_the_window_max_photos_outside_it_do_not_count(self) -> None:
        """A 40 SOL photo at −80 s is outside the 60 s window: the fall it would
        show has *stopped* (KB-0118's +0,566 R cell) and is not refused."""
        lad = ladder(dropped("9.0", (80, "40.0"), (30, "10.0"), (20, "9.5")))
        assert lad.refusal is None
        assert "peak=10.0" in rung(lad, "drop").value

    def test_the_drop_refusal_beats_the_floor_refusal(self) -> None:
        lad = ladder(
            replace(
                dropped("1.0"),
                creator_decided_by=TAPE_FLOW_SOURCE,
                unique_buyers_60s=3,
                holders_rising=False,
            )
        )
        assert lad.refusal == REFUSAL_ENTRY_AFTER_DROP


class TestTheDropThatCannotBeSeen:
    """T4.61c (review A2): T4.61b's ``peak_unknown`` was a × 0,5 discount and a
    single photo *after* the fall read as ``dd ≈ 0`` — exactly KB-0118's edge with
    the radar arriving late (soly, COVER, Punch). Now every one of those is the
    refusal ``entry_after_drop_unknown``, the 15 s lane's ``too_few_points`` rule."""

    def test_one_photo_after_the_fall_is_refused_not_passed(self) -> None:
        lad = ladder(evidence(real_sol_now=Decimal("5.0"), curve_points=photos((5, "5.0"))))
        assert lad.refusal == REFUSAL_ENTRY_AFTER_DROP_UNKNOWN
        assert lad.multiplier == Decimal(0) and lad.sol_sized == Decimal(0)
        assert "too_few_points" in rung(lad, "drop").value and "points=1" in rung(lad, "drop").value

    def test_no_photo_in_the_window_is_refused(self) -> None:
        for points in ((), photos((80, "40.0"))):  # none, or only outside the window
            lad = ladder(evidence(curve_points=points))
            assert lad.refusal == REFUSAL_ENTRY_AFTER_DROP_UNKNOWN
            assert "no_observation" in rung(lad, "drop").value

    def test_a_photo_received_after_the_instant_is_not_an_input(self) -> None:
        late = ReservePoint(
            observed_at=NOW - timedelta(seconds=20),
            received_at=NOW + timedelta(seconds=1),
            real_sol=Decimal("12.0"),
        )
        lad = ladder(evidence(curve_points=(*photos((30, "12.0")), late)))
        assert lad.refusal == REFUSAL_ENTRY_AFTER_DROP_UNKNOWN

    def test_two_photos_are_enough(self) -> None:
        assert ladder(evidence(curve_points=photos((30, "12.0"), (10, "12.0")))).refusal is None

    def test_a_failed_read_or_no_curve_read_is_refused_by_the_same_name(self) -> None:
        failed = ladder(evidence(read_failed="TimeoutError"))
        assert failed.refusal == REFUSAL_ENTRY_AFTER_DROP_UNKNOWN
        assert "read_failed:TimeoutError" in rung(failed, "drop").value
        assert ladder(evidence(real_sol_now=None)).refusal == REFUSAL_ENTRY_AFTER_DROP_UNKNOWN

    def test_unknown_beats_the_floor_refusal(self) -> None:
        lad = ladder(
            evidence(
                creator_decided_by=TAPE_FLOW_SOURCE,
                unique_buyers_60s=3,
                holders_rising=False,
                curve_points=(),
            )
        )
        assert lad.refusal == REFUSAL_ENTRY_AFTER_DROP_UNKNOWN


class TestTheFloorAndTheCap:
    def test_two_discounts_land_on_the_floor(self) -> None:
        lad = ladder(evidence(creator_decided_by=TAPE_FLOW_SOURCE, unique_buyers_60s=10))
        assert lad.multiplier == Decimal("0.25")
        assert lad.refusal is None and lad.sol_sized == Decimal("0.07")

    def test_three_discounts_are_refused_conviction_too_low(self) -> None:
        lad = ladder(
            evidence(
                creator_decided_by=TAPE_FLOW_SOURCE, unique_buyers_60s=10, holders_rising=False
            )
        )
        assert lad.multiplier == Decimal("0.125")
        assert lad.refusal == REFUSAL_CONVICTION_TOO_LOW

    def test_never_above_the_cap_nor_above_the_proposal(self) -> None:
        assert ladder(evidence(), requested=Decimal("0.5")).sol_cap == CAP
        assert ladder(evidence(), requested=Decimal("0.1")).sol_cap == Decimal("0.1")
        halved = ladder(evidence(unique_buyers_60s=1), requested=Decimal("0.5"))
        assert halved.sol_sized == Decimal("0.14"), "half of the cap, not half of 0,5"

    def test_the_size_is_quantized_down_to_the_lamport(self) -> None:
        lad = ladder(evidence(unique_buyers_60s=1), requested=Decimal("0.000000003"))
        assert lad.sol_sized == Decimal("0.000000001")


class TestTheJson:
    def test_every_rung_and_the_totals_are_written(self) -> None:
        payload = ladder(evidence(unique_buyers_60s=20)).as_json()
        assert payload["enabled"] is True and payload["evaluated"] is True
        assert payload["multiplier"] == "0.5"
        assert (payload["sol_cap"], payload["sol_sized"]) == ("0.280000000", "0.140000000")
        assert payload["refusal"] == ""
        names = [r["name"] for r in payload["rungs"]]
        assert names == ["creator", "buyers", "holders", "concentration", "drop"]
        assert payload["rungs"][1] == {
            "name": "buyers",
            "value": "20",
            "multiplier": "0.5",
            "reason": "below_min",
        }
        assert set(ConvictionConfig().as_json()) >= {"enabled", "floor", "drop_pct"}
        assert "peak_unknown_multiplier" not in ConvictionConfig().as_json()

    def test_off_writes_that_nothing_was_evaluated(self) -> None:
        assert ConvictionOutcome(None).as_json() == {"enabled": False, "evaluated": False}
        assert ConvictionOutcome(None).as_json() == LADDER_OFF
        assert ConvictionOutcome(None).input == MemeConviction()
        failed = ConvictionOutcome(ladder(evidence(read_failed="X")), read_failed="X")
        assert failed.as_json()["read_failed"] == "X"


# --- the ladder as the engine's input: check 26 and the ``conviction`` ceiling ---

AS_OF = NOW
INITIAL_REAL = 793_100_000_000_000


def _engine_inputs(
    min_trade_sol: Decimal = Decimal("0.001"),
) -> tuple[MemeWalletState, MemeLimits, CurveState, MemeContext]:
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
            "min_trade_sol": min_trade_sol,
        }
    )
    curve = CurveState(
        mint=MINT,
        # 30 SOL real on the curve: the 0,5 % impact ceiling (0,30 SOL) sits
        # above the 0,28 cap, so the ladder's ceiling is what binds.
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


def _decide(conviction: MemeConviction, *, min_trade_sol: Decimal = Decimal("0.001")):
    wallet, limits, curve, context = _engine_inputs(min_trade_sol)
    return evaluate_meme_entry(
        _proposal(Decimal("0.5")),
        wallet,
        limits,
        curve,
        context,
        MemeKillSwitchInputs(),
        live_enabled=False,
        curve_fee_pct=Decimal("0.0125"),
        creates_ata=True,
        conviction=conviction,
    )


class TestTheEngineSizesFromTheLadder:
    def test_a_discount_binds_as_conviction_and_the_request_stays_the_desks(self) -> None:
        """A4: 0,5 asked, 0,28 cap, × 0,5 ⇒ ``sol_final = 0,14`` bound by
        ``conviction`` — never ``requested`` for a clamp that is the policy's."""
        lad = ladder(evidence(unique_buyers_60s=10), requested=Decimal("0.5"))
        decision = _decide(lad.to_input())
        assert decision.approved, decision.refusals
        assert decision.sizing is not None
        assert decision.sizing.sol_final == Decimal("0.14")
        assert decision.sizing.binding_constraint == "conviction"
        assert decision.sizing.requested_sol == Decimal("0.5")
        sizing_check = next(c for c in decision.checks if c.name == "sizing")
        assert sizing_check.value == Decimal("0.14") and sizing_check.passed
        assert decision.sizing.max_sol_cost_sol == Decimal("0.1414")
        check = next(c for c in decision.checks if c.name == "conviction")
        assert check.passed and "buyers=below_min" in check.message

    def test_full_conviction_ties_with_the_trade_cap_and_the_policy_name_wins(self) -> None:
        decision = _decide(ladder(evidence(), requested=Decimal("0.5")).to_input())
        assert decision.sizing is not None
        assert decision.sizing.sol_final == CAP
        assert decision.sizing.binding_constraint == "trade_cap"
        assert "conviction" in decision.sizing.tied_limits

    @pytest.mark.parametrize(
        ("e", "name"),
        [
            (dropped("5.0"), REFUSAL_ENTRY_AFTER_DROP),
            (evidence(curve_points=()), REFUSAL_ENTRY_AFTER_DROP_UNKNOWN),
            (
                evidence(
                    creator_decided_by=TAPE_FLOW_SOURCE, unique_buyers_60s=1, holders_rising=False
                ),
                REFUSAL_CONVICTION_TOO_LOW,
            ),
        ],
    )
    def test_a_ladder_refusal_is_approved_false_with_first_refusal(
        self, e: ConvictionEvidence, name: str
    ) -> None:
        """A9: the desk and the R-studies read ``approved``/``first_refusal``; a
        ladder refusal must look like every other refusal of the engine."""
        decision = _decide(ladder(e).to_input())
        assert decision.approved is False
        assert decision.first_refusal == name
        assert decision.sizing is not None and decision.sizing.sol_final == CAP, "flat, on record"
        assert name in REFUSAL_NAMES

    def test_dust_below_the_live_floor_is_refused_conviction_too_small(self) -> None:
        """A5: 0,07 × 0,25 = 0,0175 SOL must not be sent under a 0,02 floor."""
        lad = ladder(
            evidence(creator_decided_by=TAPE_FLOW_SOURCE, unique_buyers_60s=10),
            requested=Decimal("0.07"),
        )
        assert lad.sol_sized == Decimal("0.0175") and lad.refusal is None
        decision = _decide(lad.to_input(), min_trade_sol=Decimal("0.02"))
        assert decision.approved is False
        assert decision.first_refusal == "conviction_too_small"
        sent = _decide(lad.to_input(), min_trade_sol=Decimal("0.001"))
        assert sent.approved and sent.sizing is not None
        assert sent.sizing.sol_final == Decimal("0.0175"), "the paper floor lets it through"

    def test_off_is_the_flat_size_of_before(self) -> None:
        decision = _decide(ConvictionOutcome(None).input)
        assert decision.approved and decision.sizing is not None
        assert decision.sizing.sol_final == CAP
        assert decision.sizing.binding_constraint == "trade_cap"
        assert next(c for c in decision.checks if c.name == "conviction").message == "off"


# --- the read: two bounded statements, faked at the seam, guarded ----------------


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> FakeResult:
        return self

    def all(self) -> list[dict[str, Any]]:
        return self._rows

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class FakeSession:
    def __init__(
        self, points: list[dict[str, Any]], fresh: dict[str, Any] | None, *, sleep_s: float = 0
    ) -> None:
        self.points, self.fresh, self.sleep_s = points, fresh, sleep_s
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, statement: Any, params: dict[str, Any]) -> FakeResult:
        self.calls.append((str(statement), params))
        if self.sleep_s:
            await asyncio.sleep(self.sleep_s)
        if "meme_curve_snapshots" in str(statement):
            return FakeResult(self.points)
        return FakeResult([] if self.fresh is None else [self.fresh])


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


def _point_rows(*pairs: tuple[int, str]) -> list[dict[str, Any]]:
    return [
        {
            "observed_at": p.observed_at,
            "received_at": p.received_at,
            "real_sol_reserves": p.real_sol,
        }
        for p in photos(*pairs)
    ]


FRESH = {"as_of": NOW - timedelta(seconds=8), "unique_buyers_60s": 40, "holders_rising": True}


def _patched(monkeypatch: pytest.MonkeyPatch, session: Any) -> None:
    @asynccontextmanager
    async def fake_role_session(*args: Any, **kwargs: Any) -> AsyncGenerator[Any]:
        if isinstance(session, Exception):
            raise session
        yield session

    monkeypatch.setattr(conviction_read, "role_session", fake_role_session)


async def _for(config: ConvictionConfig = ON) -> ConvictionOutcome:
    return await conviction_for(
        cast(Any, FakeCtx(FakeConfig(config))),
        cast(Any, _built()),
        cast(CurveRead, FakeCurveRead()),
        proposal=_proposal(Decimal("0.5")),
        limits=_engine_inputs()[1],
        now=NOW,
    )


class TestTheRead:
    @pytest.mark.asyncio
    async def test_two_statements_two_windows(self) -> None:
        session = FakeSession(_point_rows((45, "12.5"), (20, "9")), FRESH)
        series = await read_series_evidence(cast(Any, session), MINT, config=ON, now=NOW)
        assert len(session.calls) == 2
        (sql_points, params), (sql_fresh, _) = session.calls
        assert "meme_curve_snapshots" in sql_points and "received_at <= :now" in sql_points
        assert "meme_features_15s" in sql_fresh and "LIMIT 1" in sql_fresh
        assert params["peak_since"] == NOW - timedelta(seconds=60)
        assert params["fresh_since"] == NOW - timedelta(seconds=120)
        assert params["now"] == NOW and params["mint"] == MINT
        assert [p.real_sol for p in series["points"]] == [Decimal("12.5"), Decimal("9")]
        assert series["unique_buyers_60s"] == 40

    @pytest.mark.asyncio
    async def test_no_rows_is_an_empty_series(self) -> None:
        session = FakeSession([], None)
        series = await read_series_evidence(cast(Any, session), MINT, config=ON, now=NOW)
        assert series == {"points": ()}

    def test_evidence_from_the_admission_and_the_series(self) -> None:
        series = {"points": photos((45, "12.8"), (20, "12.0")), **FRESH, "holders_rising": False}
        e = evidence_from(cast(Any, _built(TAPE_FLOW_SOURCE)), cast(Any, FakeCurveRead()), series)
        assert e.creator_decided_by == TAPE_FLOW_SOURCE
        assert e.unique_buyers_60s == 40 and e.holders_rising is False
        assert e.real_sol_now == Decimal("6.4") and len(e.curve_points) == 2
        assert e.bundled_share_pct == Decimal("0.05") and e.top10_share_pct == Decimal("0.15")
        # 6,4 against a 12,8 peak is exactly the 50 % drop.
        assert ladder(e).refusal == REFUSAL_ENTRY_AFTER_DROP

    def test_evidence_with_nothing_measured_is_all_none(self) -> None:
        e = evidence_from(
            cast(Any, FakeBuilt(_engine_inputs()[3], {})), cast(Any, FakeCurveRead()), {}
        )
        assert e.creator_decided_by is None and e.unique_buyers_60s is None
        assert e.holders_rising is None and e.curve_points == ()
        assert ladder(e).refusal == REFUSAL_ENTRY_AFTER_DROP_UNKNOWN

    @pytest.mark.asyncio
    async def test_on_reads_once_and_judges(self, monkeypatch: pytest.MonkeyPatch) -> None:
        session = FakeSession(_point_rows((30, "6.4"), (10, "6.4")), FRESH)
        _patched(monkeypatch, session)
        outcome = await _for()
        assert len(session.calls) == 2
        assert outcome.ladder is not None and outcome.read_failed is None
        assert outcome.ladder.refusal is None and outcome.ladder.sol_sized == CAP
        assert outcome.input == MemeConviction(
            enabled=True,
            multiplier=Decimal(1),
            sol_sized=CAP,
            detail=outcome.input.detail,
        )

    @pytest.mark.asyncio
    async def test_off_opens_no_session_and_judges_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A1, zero cost: with the flag off the read is not even attempted."""
        _patched(monkeypatch, AssertionError("a session was opened with the flag off"))
        outcome = await _for(ConvictionConfig())
        assert outcome.ladder is None and outcome.as_json() == LADDER_OFF
        assert outcome.input.enabled is False

    @pytest.mark.asyncio
    async def test_on_a_read_that_raises_is_a_refusal_never_an_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A1: T4.61b let a locked partition raise through ``entries_once`` and
        take the exits loop down with it. Now it is logged and judged as the drop
        the ladder cannot see."""
        _patched(monkeypatch, RuntimeError("partition locked"))
        outcome = await _for()
        assert outcome.read_failed == "RuntimeError"
        assert outcome.ladder is not None
        assert outcome.ladder.refusal == REFUSAL_ENTRY_AFTER_DROP_UNKNOWN
        assert outcome.as_json()["read_failed"] == "RuntimeError"
        assert outcome.input.refusal == REFUSAL_ENTRY_AFTER_DROP_UNKNOWN

    @pytest.mark.asyncio
    async def test_on_a_read_that_hangs_is_cut_by_its_own_deadline(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(conviction_read, "READ_TIMEOUT_S", 0.02)
        _patched(monkeypatch, FakeSession([], None, sleep_s=2.0))
        outcome = await asyncio.wait_for(_for(), timeout=1.0)
        assert outcome.read_failed == "timeout"
        assert outcome.ladder is not None
        assert outcome.ladder.refusal == REFUSAL_ENTRY_AFTER_DROP_UNKNOWN


# --- the 30 s cooldown of ``entry_after_drop`` ----------------------------------


class TestTheDropCooldown:
    OTHER = "2nG3hY94XM3zwf4rtuVkTvLGCJgBfcCggARUAkFSpump"

    def test_the_short_cooldowns_are_real_refusals_and_not_deterministic_ones(self) -> None:
        # T4.78 added ``mint_cooldown_after_loss`` (300 s, matched by base name).
        assert SHORT_COOLDOWNS == {"entry_after_drop": 30.0, "mint_cooldown_after_loss": 300.0}
        assert set(SHORT_COOLDOWNS) <= REFUSAL_NAMES
        assert not set(SHORT_COOLDOWNS) & DETERMINISTIC_REFUSALS
        assert "entry_after_drop_unknown" not in SHORT_COOLDOWNS, "the next photo can answer"
        assert "conviction_too_low" not in SHORT_COOLDOWNS, "changes with every 15 s row"

    def test_a_drop_refused_twenty_seconds_ago_cools_forty_does_not(self) -> None:
        rows = [(MINT, "entry_after_drop", NOW - timedelta(seconds=20))]
        assert cooling_mints_by_window(rows, now=NOW, cooldown_s=120.0) == frozenset({MINT})
        rows = [(MINT, "entry_after_drop", NOW - timedelta(seconds=40))]
        assert cooling_mints_by_window(rows, now=NOW, cooldown_s=120.0) == frozenset()

    def test_the_deterministic_refusals_keep_the_owners_window(self) -> None:
        rows = [(MINT, "progress_above_window", NOW - timedelta(seconds=100))]
        assert cooling_mints_by_window(rows, now=NOW, cooldown_s=120.0) == frozenset({MINT})
        rows = [(MINT, "progress_above_window", NOW - timedelta(seconds=130))]
        assert cooling_mints_by_window(rows, now=NOW, cooldown_s=120.0) == frozenset()

    def test_the_owners_cooldown_caps_the_short_one_and_other_reasons_never_cool(self) -> None:
        rows = [
            (MINT, "entry_after_drop", NOW - timedelta(seconds=20)),
            (self.OTHER, "entry_after_drop_unknown", NOW - timedelta(seconds=5)),
            (self.OTHER, "conviction_too_low", NOW - timedelta(seconds=5)),
            (self.OTHER, "curve_state_stale", NOW - timedelta(seconds=5)),
        ]
        assert cooling_mints_by_window(rows, now=NOW, cooldown_s=120.0) == frozenset({MINT})
        assert cooling_mints_by_window(rows, now=NOW, cooldown_s=10.0) == frozenset()
