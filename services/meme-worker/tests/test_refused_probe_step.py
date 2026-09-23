"""T4.85 / EXP-M23 — the wiring of ``refused_probe_v0/1``: what the tick hands
the sampler, what the sampler's pick becomes, and the regression that none of
this reaches a real-money path.

Fakes only: no database, no clock, no network. The session below answers the
two statements this lane issues (the "has this mint ever been probed" read and
the proposal insert) and records what it was asked to write.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from hunter_indicators.meme.curve import CurveReserves
from hunter_meme_worker.event_gate_caches import EventGateCaches, refresh_event_gate_caches
from hunter_meme_worker.lab_fast import fast_gate_step
from hunter_meme_worker.lab_models import CLOCKS, RuleSetSpec, Snapshot
from hunter_meme_worker.lab_repo import _RULE_SETS  # pyright: ignore[reportPrivateUsage]
from hunter_meme_worker.launch_lane_repo import LaunchRuleSpec
from hunter_meme_worker.proposals import GateRow
from hunter_meme_worker.refused_probe import PROBE_CLOCK, RefusedRow, pick_probes
from hunter_meme_worker.refused_probe_step import (
    RefusedProbeState,
    probe_drafts,
    probe_spec_of,
    refused_row_of,
    run_refused_probe,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Sequence

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 23, 16, 20, tzinfo=UTC)
NOW = T0 + timedelta(seconds=5)
PROBE_ID = "01994d00-6c1a-7000-8000-00000000001c"
OPERATOR_ID = "01994d00-6c1a-7000-8000-000000000019"

MINT_IN = "Mint7111111111111111111111111111111111111111"
"""Frozen draw 0,0838 — drawn at stratum A's 10 %."""
MINT_OUT = "Mint5111111111111111111111111111111111111111"
"""Frozen draw 0,9251 — never drawn."""

DESK_EXIT: dict[str, Any] = {
    "size_sol": "0.07",
    "target_x": "1.15",
    "trailing_pct": "10",
    "trailing_arm_x": None,
    "max_hold_s": 300,
    "exit_on_line_break": True,
    "max_sol_per_bet": "0.07",
    "max_exposure_per_mint_sol": "0.07",
    "fee_pct": "1.75",
}
"""``operator/6``'s own exit and cost (``0055``) — the desk's, not
``flow_v2``'s 3× / 1800 s, which is caveat nº 1 of R67."""

_GATE: dict[str, Any] = {
    "gate_key": "recusadas_da_mesa",
    "gate_version": 1,
    "exit_key": "alvo_1_15x_trailing_10_tempo_5m",
    "exit_version": 1,
    "min_age_s": 30,
    "max_age_s": 300,
    "min_progress_pct": "5",
    "max_progress_pct": "100",
    "max_participation_pct": "1",
    "max_loss_pct": "50",
    "line_break_snapshots": 2,
    "wallet_max_sol": "100.0",
    "daily_loss_cap_sol": "10.0",
    "max_open_positions": 25,
    "priority_fee_sol": "0",
    "ttl_s": 180,
}


def _spec(clock: str = PROBE_CLOCK, status: str = "active", **overrides: Any) -> RuleSetSpec:
    return RuleSetSpec.from_params(
        id=PROBE_ID,
        name="refused_probe_v0",
        version="1",
        kind="research_only",
        exp_ref="EXP-M23",
        status=status,
        code_ref="hunter_meme_worker.refused_probe:pick_probes",
        params={**_GATE, **DESK_EXIT, "clock": clock, **overrides},
    )


def _desk() -> RuleSetSpec:
    return RuleSetSpec.from_params(
        id=OPERATOR_ID,
        name="operator",
        version="6",
        kind="operator",
        exp_ref=None,
        status="active",
        code_ref="hunter_indicators.meme.rules:evaluate_entry+evaluate_exit",
        params={**_GATE, **DESK_EXIT, "clock": "15s", "gate_key": "fluxo_e_holders"},
    )


def _snapshot(mint: str, at: datetime) -> Snapshot:
    return Snapshot(
        mint=mint,
        observed_at=at,
        source="pumpfun_rest",
        reserves=CurveReserves(
            virtual_sol_reserves=Decimal(34),
            virtual_token_reserves=Decimal(946_000_000),
            real_token_reserves=Decimal(666_100_000),
            initial_real_token_reserves=Decimal(793_100_000),
        ),
        real_sol_reserves=Decimal(4),
        total_supply=Decimal(1_000_000_000),
        complete=False,
        mcap_sol=Decimal("35.94"),
    )


def _gate_row(mint: str = MINT_IN, *, at: datetime | None = None, **overrides: Any) -> GateRow:
    as_of = T0 if at is None else at
    base: dict[str, Any] = {
        "mint": mint,
        "end_time": as_of,
        "created_at": as_of - timedelta(seconds=120),
        "curve_progress_pct": Decimal("0.160000"),
        "progress_reason": None,
        "mcap_sol": Decimal("35.94"),
        "creator_sold": False,
        "curve_volume_1m_sol": Decimal(10),
        "completed_at": None,
        "migrated_at": None,
        "snapshot": _snapshot(mint, as_of - timedelta(seconds=3)),
        "mayhem_enabled": False,
        "series": "meme_features_15s_v1",
        "computed_at": as_of,
        "tape_as_of": as_of,
    }
    base.update(overrides)
    return GateRow(**base)


class _Result:
    def __init__(self, rows: Sequence[Any]) -> None:
        self._rows = list(rows)

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[Any]:
        return list(self._rows)


class FakeSession:
    """Answers the probe lane's two statements and records the inserts."""

    def __init__(self, *, already_probed: Sequence[str] = ()) -> None:
        self.already_probed = list(already_probed)
        self.inserted: list[dict[str, Any]] = []

    async def execute(self, _statement: Any, params: Any = None) -> _Result:
        if params is not None and "mints" in params:
            asked = set(params["mints"])
            return _Result([m for m in self.already_probed if m in asked])
        assert params is not None
        self.inserted.append(dict(params))
        return _Result([params["id"]])


def _refused(mint: str = MINT_IN, *, at: datetime | None = None) -> RefusedRow:
    row = refused_row_of(_desk(), _gate_row(mint, at=at), Counter({"snipers_above_max": 1}))
    assert row is not None
    return row


# --- what the tick hands the sampler ----------------------------------------


def test_a_structural_skip_never_becomes_an_opportunity() -> None:
    assert refused_row_of(_desk(), _gate_row(), Counter({"already_open": 1})) is None
    assert refused_row_of(_desk(), _gate_row(), Counter()) is None


def test_the_row_carries_the_three_provenance_stamps_of_its_instant() -> None:
    row = _refused()
    assert row.as_of == T0
    assert row.computed_at == T0
    assert row.tape_as_of == T0
    assert row.snapshot_observed_at == T0 - timedelta(seconds=3)
    assert row.refused_by == "operator/6"


def test_every_reason_of_the_instant_travels_not_only_the_first() -> None:
    row = refused_row_of(
        _desk(),
        _gate_row(),
        Counter({"snipers_above_max": 1, "holders_below_min": 1, "already_open": 0}),
    )
    assert row is not None
    assert row.refusals == ("holders_below_min", "snipers_above_max")


# --- what the pick becomes --------------------------------------------------


def test_the_draft_is_born_approved_research_only_and_carries_the_desks_exit() -> None:
    spec = _spec()
    row = _gate_row()
    (pick,) = pick_probes([_refused()], admitted={}, now=NOW)
    (draft,) = probe_drafts(spec, [pick], {(MINT_IN, T0): row}, now=NOW, ttl_s=180)
    assert draft.status == "approved"
    assert draft.decided_by == "rules"
    assert draft.features_end_time == T0
    assert draft.suggested["size_sol"] == "0.07"
    assert draft.suggested["target_x"] == "1.15"
    assert draft.suggested["trailing_pct"] == "10"
    assert draft.suggested["max_hold_s"] == 300
    assert draft.suggested["exit_on_line_break"] is True
    assert draft.decision == dict(draft.suggested)
    assert spec.trailing_arm_x is None, "trailing armed at the entry, not at 1,5x"


def test_the_probe_block_is_the_first_reason_and_carries_probability_and_stratum() -> None:
    (pick,) = pick_probes([_refused()], admitted={}, now=NOW)
    (draft,) = probe_drafts(_spec(), [pick], {(MINT_IN, T0): _gate_row()}, now=NOW, ttl_s=180)
    block = draft.reasons[0]
    assert block["probe"] == "refused_probe_v0/1"
    assert block["stratum"] == "A"
    assert block["inclusion_probability"] == "0.10"
    assert block["refusals"] == ["snipers_above_max"]
    assert any("feature" in reason for reason in draft.reasons[1:]), "the features too"


def test_a_later_photo_does_not_move_the_bet() -> None:
    """The invariance the anti-look-ahead guard exists for, at the step level."""
    early = _refused(at=T0)
    late = _refused(at=T0 + timedelta(seconds=15))
    rows = {
        (MINT_IN, T0): _gate_row(),
        (MINT_IN, T0 + timedelta(seconds=15)): _gate_row(at=T0 + timedelta(seconds=15)),
    }
    before = probe_drafts(
        _spec(), pick_probes([early], admitted={}, now=NOW), rows, now=NOW, ttl_s=180
    )
    after = probe_drafts(
        _spec(),
        pick_probes([early, late], admitted={}, now=NOW),
        rows,
        now=NOW,
        ttl_s=180,
    )
    assert [d.features_end_time for d in before] == [d.features_end_time for d in after] == [T0]
    assert [d.quote for d in before] == [d.quote for d in after]


# --- one bet per mint, ever -------------------------------------------------


@pytest.mark.asyncio
async def test_the_drawn_mint_becomes_a_proposal_and_is_remembered() -> None:
    session = FakeSession()
    state = RefusedProbeState()
    written = await run_refused_probe(
        session,  # type: ignore[arg-type]
        state,
        _spec(),
        rows=[_gate_row()],
        refused=[_refused()],
        admitted={},
        now=NOW,
        ttl_s=180,
    )
    assert written == 1
    assert session.inserted[0]["mint"] == MINT_IN
    assert session.inserted[0]["rule_set_id"] == PROBE_ID
    assert MINT_IN in state.drawn


@pytest.mark.asyncio
async def test_a_mint_decided_in_an_earlier_tick_is_never_drawn_again() -> None:
    session = FakeSession()
    state = RefusedProbeState(drawn={MINT_IN: T0})
    written = await run_refused_probe(
        session,  # type: ignore[arg-type]
        state,
        _spec(),
        rows=[_gate_row()],
        refused=[_refused()],
        admitted={},
        now=NOW,
        ttl_s=180,
    )
    assert (written, session.inserted) == (0, [])


@pytest.mark.asyncio
async def test_a_mint_already_probed_in_the_database_is_never_probed_twice() -> None:
    """The durable half of "one bet per mint, ever": a restart empties the
    in-memory memory, the ``meme_proposals`` row does not."""
    session = FakeSession(already_probed=[MINT_IN])
    written = await run_refused_probe(
        session,  # type: ignore[arg-type]
        RefusedProbeState(),
        _spec(),
        rows=[_gate_row()],
        refused=[_refused()],
        admitted={},
        now=NOW,
        ttl_s=180,
    )
    assert (written, session.inserted) == (0, [])


@pytest.mark.asyncio
async def test_a_mint_admitted_in_the_same_tick_is_not_probed() -> None:
    session = FakeSession()
    written = await run_refused_probe(
        session,  # type: ignore[arg-type]
        RefusedProbeState(),
        _spec(),
        rows=[_gate_row()],
        refused=[_refused()],
        admitted={MINT_IN: T0},
        now=NOW,
        ttl_s=180,
    )
    assert (written, session.inserted) == (0, [])


@pytest.mark.asyncio
async def test_a_mint_the_lottery_did_not_draw_is_still_remembered() -> None:
    """Otherwise the mint gets a fresh lottery every 15 s and the probability
    written on the bets stops being the probability that produced them."""
    session = FakeSession()
    state = RefusedProbeState()
    written = await run_refused_probe(
        session,  # type: ignore[arg-type]
        state,
        _spec(),
        rows=[_gate_row(MINT_OUT)],
        refused=[_refused(MINT_OUT)],
        admitted={},
        now=NOW,
        ttl_s=180,
    )
    assert (written, session.inserted) == (0, [])
    assert MINT_OUT in state.drawn


@pytest.mark.asyncio
async def test_without_the_seeded_arm_the_lane_is_a_no_op() -> None:
    """Before ``0060`` is applied there is no probe set, and this must cost
    the tick nothing at all — not even a read."""
    session = FakeSession()
    written = await run_refused_probe(
        session,  # type: ignore[arg-type]
        RefusedProbeState(),
        None,
        rows=[_gate_row()],
        refused=[_refused()],
        admitted={},
        now=NOW,
        ttl_s=180,
    )
    assert (written, session.inserted) == (0, [])


def test_the_memory_is_pruned_so_a_long_running_worker_does_not_grow_it() -> None:
    state = RefusedProbeState(drawn={MINT_OUT: T0 - timedelta(days=1), MINT_IN: T0})
    state.remember([MINT_IN], now=NOW)
    assert MINT_OUT not in state.drawn
    assert MINT_IN in state.drawn


# --- the regression: nothing real changed -----------------------------------


def test_probe_spec_of_finds_only_an_active_set_on_the_probe_clock() -> None:
    probe, desk = _spec(), _desk()
    assert probe_spec_of([desk, probe]) is probe
    assert probe_spec_of([desk]) is None
    assert probe_spec_of([_spec(status="retired")]) is None


def test_the_probe_clock_is_its_own_and_no_existing_lane_selects_it() -> None:
    assert PROBE_CLOCK in CLOCKS
    assert PROBE_CLOCK not in {"1m", "15s", "event"}
    # the launch lane refuses it by name
    with pytest.raises(ValueError, match="not a launch-lane set"):
        LaunchRuleSpec.from_params(
            id=PROBE_ID,
            name="refused_probe_v0",
            version="1",
            kind="research_only",
            exp_ref="EXP-M23",
            status="active",
            params={
                "clock": PROBE_CLOCK,
                "size_sol": "0.07",
                "max_creator_initial_sol": "1",
                "exit_key": "x",
                "time_stop_s": 300,
                "max_drawdown_from_peak_pct": "50",
            },
        )
    # the event lane's cache keeps only the 15-second sets
    caches = EventGateCaches()
    refresh_event_gate_caches(
        caches, specs=[_spec()], rows=[], open_mints={}, pedigree={}, e2b={}, now=NOW
    )
    assert caches.specs == ()
    # and the loader still loads it: only ``clock = 'event'`` is subtracted
    assert "<> 'event'" in str(_RULE_SETS)
    assert PROBE_CLOCK not in str(_RULE_SETS)


@pytest.mark.asyncio
async def test_the_fast_lane_does_not_evaluate_the_probe_set() -> None:
    """``fast_gate_step`` over a spec list that is only the probe returns
    without opening a session — the desk's own path is untouched."""

    class Boom:
        def __call__(self) -> None:
            raise AssertionError("the probe must not make the fast lane open a session")

    class _Ctx:
        session_factory = Boom()

    assert await fast_gate_step(_Ctx(), [_spec()], {}, now=NOW) == (0, 0)  # type: ignore[arg-type]


def test_the_heartbeat_names_what_the_probe_measured() -> None:
    """Refutation rule 1 of the pre-registration — "abandonar se o braço
    produzir < 20 mints medidos/dia" — needs the two numbers visible without a
    query."""
    from hunter_meme_worker.lab import LabState
    from hunter_meme_worker.lab_heartbeat import heartbeat_fields

    state = LabState()
    state.probe.considered_total = 412
    state.probe.proposals_total = 37
    fields = heartbeat_fields(state)
    assert fields["lab_refused_probe_considered"] == "412"
    assert fields["lab_refused_probe_proposals"] == "37"
    state.probe.unquotable_total = 9
    assert heartbeat_fields(state)["lab_refused_probe_unquotable"] == "9"


# --- Astra's review of 23/09/2026: the experiment must not cost the desk ----


@pytest.mark.asyncio
async def test_a_probe_failure_never_reaches_the_desks_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``role_session`` is one transaction. Before this, a statement timeout on
    the probe's read would have rolled back ``operator/5`` and ``operator/6``'s
    proposals of the same tick — the experiment undoing the desk's work."""
    from contextlib import asynccontextmanager

    from hunter_meme_worker import lab_fast
    from hunter_meme_worker.config import MemeConfig

    opened: list[str] = []

    @asynccontextmanager
    async def _boom(*_args: Any, **_kwargs: Any) -> AsyncGenerator[Any]:
        opened.append("probe")
        raise TimeoutError("canceling statement due to statement timeout")
        yield  # pragma: no cover

    monkeypatch.setattr(lab_fast, "role_session", _boom)
    ctx = SimpleNamespace(
        config=MemeConfig(enabled=True, lab_enabled=True),
        session_factory=None,
        state=SimpleNamespace(probe=RefusedProbeState()),
    )
    await lab_fast._probe_step(  # pyright: ignore[reportPrivateUsage]
        ctx,  # type: ignore[arg-type]
        [_spec()],
        rows=[_gate_row()],
        refused=[_refused()],
        admitted={},
        now=NOW,
        pedigree={},
        e2b={},
    )
    assert opened == ["probe"], "the probe did open its own transaction"


@pytest.mark.asyncio
async def test_without_the_arm_the_probe_opens_no_transaction_at_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from contextlib import asynccontextmanager

    from hunter_meme_worker import lab_fast
    from hunter_meme_worker.config import MemeConfig

    @asynccontextmanager
    async def _never(*_args: Any, **_kwargs: Any) -> AsyncGenerator[Any]:
        raise AssertionError("no arm seeded: the probe must not touch the database")
        yield  # pragma: no cover

    monkeypatch.setattr(lab_fast, "role_session", _never)
    ctx = SimpleNamespace(
        config=MemeConfig(enabled=True, lab_enabled=True),
        session_factory=None,
        state=SimpleNamespace(probe=RefusedProbeState()),
    )
    await lab_fast._probe_step(  # pyright: ignore[reportPrivateUsage]
        ctx,  # type: ignore[arg-type]
        [_desk()],
        rows=[_gate_row()],
        refused=[_refused()],
        admitted={},
        now=NOW,
        pedigree={},
        e2b={},
    )


def test_the_desks_pedigree_subtracts_this_arms_paper_bets() -> None:
    """Astra's finding nº 7: the probe follows coins the desk REFUSED, so its
    own paper bets make the creator watcher stamp ``creator_sold_seen_at`` on
    mints nobody was watching — and ``creator_prior_dump_count`` counted every
    paper bet. A later coin of that creator would then be refused
    ``creator_repeat_dumper`` on the **real desk** because of the experiment."""
    from hunter_meme_worker.lab_repo_fast import _PEDIGREE  # pyright: ignore[reportPrivateUsage]
    from hunter_meme_worker.refused_probe import PROBE_RULE_SET_ID

    sql = str(_PEDIGREE)
    assert sql.count("pb.rule_set_id <> :probe_rule_set_id") == 1
    assert sql.count("pb2.rule_set_id <> :probe_rule_set_id") == 1
    assert PROBE_RULE_SET_ID == PROBE_ID, "the id the query subtracts is 0060's own"


@pytest.mark.asyncio
async def test_an_unquotable_refusal_is_counted_not_silently_dropped() -> None:
    """Astra's finding nº 6: a refusal with no photo cannot be priced, so it is
    not an opportunity — but EXP-M23 forbids a silent exclusion (its own
    refutation rule 2 is about coverage artefacts), so it is counted."""
    session = FakeSession()
    state = RefusedProbeState()
    blind = RefusedRow(
        mint=MINT_IN, as_of=T0, refusals=("snipers_above_max",), refused_by="operator/6"
    )
    written = await run_refused_probe(
        session,  # type: ignore[arg-type]
        state,
        _spec(),
        rows=[_gate_row()],
        refused=[blind],
        admitted={},
        now=NOW,
        ttl_s=180,
    )
    assert (written, session.inserted) == (0, [])
    assert state.unquotable_total == 1
    assert MINT_IN not in state.drawn, "it never had an opportunity, so it keeps its lottery"
