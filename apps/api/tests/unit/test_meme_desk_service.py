"""``services/meme_desk.py`` — state transitions, the named 409/422 refusals,
``Idempotency-Key`` replay and the audit row (T4.7). No database, no Redis:
an in-memory repository/store stand in; the same use cases run against a
real Postgres in ``tests/integration/test_meme_desk_repository.py``.

Contract: ``.claude/state/contrato-T4.6-T4.7-mesa-meme.md`` §Rotas.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest
from pydantic import ValidationError

from hunter_api.auth.principal import Principal
from hunter_api.auth.rbac import OrgContext
from hunter_api.repositories.meme_desk import MemeDeskRepository
from hunter_api.repositories.meme_desk_rows import (
    BetRow,
    CommandRow,
    CurveQuoteRow,
    DeskRow,
    InvalidDeskCursorError,
    ProposalRow,
    RuleSetRow,
    TokenIdentity,
    decode_desk_cursor,
    encode_desk_cursor,
)
from hunter_api.schemas.meme_desk import ApproveProposalIn, ManualProposalIn, RejectProposalIn
from hunter_api.services.meme_desk import (
    BetNotFoundError,
    BetStateConflictError,
    DeskRefusedError,
    ProposalNotFoundError,
    ProposalStateConflictError,
    approve_proposal,
    cancel_proposal,
    file_manual_proposal,
    reject_proposal,
    sell_now,
)
from hunter_api.services.meme_desk_idempotency import DeskReplayConflictError
from hunter_api.services.meme_desk_out import MANUAL_QUOTE_FEE_PCT, build_manual_quote
from hunter_core.audit import InMemoryAuditSink, use_audit_sink
from hunter_core.domain.enums import OrganizationRole

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 12, 7, 30, tzinfo=UTC)
ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
CLERK_ID = "user_FAKE_operator"
MINT = "Fh42kAfy27CGoUA8CgFwpTGMubzndaAyTy2gghu5pump"
MINT_DONE = "Synthetic1CompletedNotMigratedxxxxxxxxxxxxx"
KEY = "desk-key-000001"


def _context() -> OrgContext:
    principal = Principal(user_id=USER_ID, external_auth_id=CLERK_ID)
    return OrgContext(org_id=ORG_ID, role=OrganizationRole.TRADER, principal=principal)


def _rule_set(**overrides: Any) -> RuleSetRow:
    base: dict[str, Any] = {
        "id": uuid.uuid4(),
        "name": "operator",
        "version": "1",
        "kind": "operator",
        "params": {"max_sol_per_bet": "0.5", "wallet_max_sol": "5", "daily_loss_cap_sol": "1"},
        "status": "active",
    }
    base.update(overrides)
    return RuleSetRow(**base)


def _proposal(rule_set: RuleSetRow, **overrides: Any) -> ProposalRow:
    base: dict[str, Any] = {
        "id": uuid.uuid4(),
        "mint": MINT,
        "rule_set_id": rule_set.id,
        "origin": "rules",
        "status": "proposed",
        "proposed_at": NOW - timedelta(seconds=30),
        "expires_at": NOW + timedelta(seconds=90),
        "features_end_time": NOW - timedelta(minutes=1),
        "quote": {"observed_at": (NOW - timedelta(seconds=40)).isoformat(), "source": "solana_rpc"},
        "reasons": ["progress_gate"],
        "suggested": {
            "size_sol": "0.2",
            "target_x": "2",
            "trailing_pct": "30",
            "max_hold_s": 900,
        },
        "decision": None,
        "decided_by": None,
        "decided_at": None,
        "bet_id": None,
        "refusal": None,
    }
    base.update(overrides)
    return ProposalRow(**base)


def _bet(rule_set: RuleSetRow, proposal_id: uuid.UUID, **overrides: Any) -> BetRow:
    base: dict[str, Any] = {
        "id": uuid.uuid4(),
        "proposal_id": proposal_id,
        "rule_set_id": rule_set.id,
        "mint": MINT,
        "mode": "paper",
        "status": "open",
        "entry_at": NOW - timedelta(minutes=2),
        "entry": {"sol_spent": "0.2", "fee_sol": "0.0035", "tokens": "1000"},
        "initial_risk_sol": Decimal("0.2"),
        "params": {"size_sol": "0.2", "target_x": "2", "trailing_pct": "30", "max_hold_s": 900},
        "exit_at": None,
        "exit": None,
        "pnl_sol": None,
        "r_multiple": None,
        "mark_sol": Decimal("0.21"),
        "mark_at": NOW - timedelta(seconds=10),
        "high_water_x": Decimal("1.1"),
        "sol_usd_at_entry": Decimal("180"),
        "sol_usd_at_exit": None,
    }
    base.update(overrides)
    return BetRow(**base)


class FakeStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def load(self, key: str) -> str | None:
        return self.values.get(key)

    async def save(self, key: str, value: str, *, ttl_s: int) -> None:
        del ttl_s
        self.values.setdefault(key, value)


class FakeRepository:
    """Duck-types the slice of ``MemeDeskRepository`` the use cases call."""

    def __init__(self) -> None:
        self.rule_sets: dict[uuid.UUID, RuleSetRow] = {}
        self.proposals: dict[uuid.UUID, ProposalRow] = {}
        self.bets: dict[uuid.UUID, BetRow] = {}
        self.commands: dict[uuid.UUID, CommandRow] = {}
        self.tokens: dict[str, TokenIdentity] = {}
        self.quotes: dict[str, CurveQuoteRow] = {}
        self.decide_calls = 0

    async def get_proposal(self, proposal_id: uuid.UUID) -> ProposalRow | None:
        return self.proposals.get(proposal_id)

    async def get_rule_set(self, rule_set_id: uuid.UUID) -> RuleSetRow | None:
        return self.rule_sets.get(rule_set_id)

    async def get_operator_rule_set(self) -> RuleSetRow | None:
        for rule_set in self.rule_sets.values():
            if (rule_set.name, rule_set.version) == ("operator", "1"):
                return rule_set
        return None

    async def get_bet(self, bet_id: uuid.UUID) -> BetRow | None:
        return self.bets.get(bet_id)

    async def get_token(self, mint: str) -> TokenIdentity | None:
        return self.tokens.get(mint)

    async def latest_curve_quote(self, mint: str) -> CurveQuoteRow | None:
        return self.quotes.get(mint)

    async def latest_features_end_time(self, mint: str) -> datetime | None:
        del mint
        return None

    async def get_command(self, command_id: uuid.UUID) -> CommandRow | None:
        return self.commands.get(command_id)

    async def pending_command(self, *, bet_id: uuid.UUID, command: str) -> CommandRow | None:
        for row in self.commands.values():
            if row.bet_id == bet_id and row.command == command and row.applied_at is None:
                return row
        return None

    async def desk_row(self, proposal_id: uuid.UUID) -> DeskRow | None:
        proposal = self.proposals.get(proposal_id)
        if proposal is None:
            return None
        bet = self.bets.get(proposal.bet_id) if proposal.bet_id is not None else None
        return DeskRow(
            proposal=proposal,
            token=self.tokens.get(proposal.mint),
            bet=bet,
            rule_set=self.rule_sets.get(proposal.rule_set_id),
            rank=0,
        )

    async def decide_proposal(
        self,
        proposal_id: uuid.UUID,
        *,
        status: str,
        decision: dict[str, Any] | None,
        decided_by: str,
        decided_at: datetime,
        mode: str = "paper",
    ) -> bool:
        self.decide_calls += 1
        current = self.proposals[proposal_id]
        if current.status != "proposed":
            return False
        self.proposals[proposal_id] = replace(
            current,
            status=status,
            decision=decision,
            decided_by=decided_by,
            decided_at=decided_at,
            mode=mode,
        )
        return True

    async def insert_proposal(self, row: ProposalRow) -> None:
        self.proposals[row.id] = row

    async def insert_command(self, row: CommandRow) -> None:
        self.commands[row.id] = row


def _world() -> tuple[FakeRepository, FakeStore, RuleSetRow, ProposalRow]:
    repo = FakeRepository()
    rule_set = _rule_set()
    repo.rule_sets[rule_set.id] = rule_set
    proposal = _proposal(rule_set)
    repo.proposals[proposal.id] = proposal
    repo.tokens[MINT] = TokenIdentity(
        mint=MINT,
        name="bum bum",
        symbol="bam bum",
        creator="s9uu4shkYUQUmnWN2jkwgA2Nbg2Rmv7vUprtjy71xgP",
        created_at=NOW - timedelta(minutes=6),
        mayhem_enabled=True,
        mayhem_state="active",
        completed_at=None,
        migrated_at=None,
    )
    repo.tokens[MINT_DONE] = replace(repo.tokens[MINT], mint=MINT_DONE, completed_at=NOW)
    repo.quotes[MINT] = CurveQuoteRow(
        observed_at=NOW - timedelta(seconds=20),
        source="solana_rpc",
        virtual_sol_reserves=Decimal("9.8"),
        virtual_token_reserves=Decimal("1071000000"),
        real_token_reserves=Decimal("791100000"),
        mcap_sol=Decimal("9.14"),
        complete=False,
    )
    return repo, FakeStore(), rule_set, proposal


def _approve_body(**overrides: Any) -> ApproveProposalIn:
    base: dict[str, Any] = {
        "size_sol": "0.2",
        "target_x": "2",
        "trailing_pct": "30",
        "max_hold_s": 900,
        "note": "ok",
    }
    base.update(overrides)
    return ApproveProposalIn.model_validate(base)


def _repo(repo: FakeRepository) -> MemeDeskRepository:
    return cast(MemeDeskRepository, repo)


class TestApprove:
    async def test_proposed_becomes_approved_with_the_operators_decision(self) -> None:
        repo, store, _, proposal = _world()
        out = await approve_proposal(
            _repo(repo),
            store,
            context=_context(),
            proposal_id=proposal.id,
            idempotency_key=KEY,
            body=_approve_body(size_sol="0.3"),
            now=NOW,
        )
        assert out.row.status == "approved"
        assert out.row.decided_by == CLERK_ID
        assert out.row.decided_at == NOW
        assert out.row.decision is not None
        assert out.row.decision.size_sol == Decimal("0.3")
        assert out.row.decision.max_hold_s == 900
        assert out.row.decision.note == "ok"
        assert repo.proposals[proposal.id].decision == {
            "size_sol": "0.3",
            "target_x": "2",
            "trailing_pct": "30",
            "max_hold_s": 900,
            "note": "ok",
        }

    async def test_replay_of_the_same_key_returns_the_same_result_without_a_second_write(
        self,
    ) -> None:
        repo, store, _, proposal = _world()
        first = await approve_proposal(
            _repo(repo),
            store,
            context=_context(),
            proposal_id=proposal.id,
            idempotency_key=KEY,
            body=_approve_body(),
            now=NOW,
        )
        second = await approve_proposal(
            _repo(repo),
            store,
            context=_context(),
            proposal_id=proposal.id,
            idempotency_key=KEY,
            body=_approve_body(),
            now=NOW + timedelta(seconds=5),
        )
        assert second == first
        assert repo.decide_calls == 1

    async def test_same_key_with_a_different_body_is_a_409(self) -> None:
        repo, store, _, proposal = _world()
        await approve_proposal(
            _repo(repo),
            store,
            context=_context(),
            proposal_id=proposal.id,
            idempotency_key=KEY,
            body=_approve_body(),
            now=NOW,
        )
        with pytest.raises(DeskReplayConflictError, match="desk_replay_conflict"):
            await approve_proposal(
                _repo(repo),
                store,
                context=_context(),
                proposal_id=proposal.id,
                idempotency_key=KEY,
                body=_approve_body(size_sol="0.4"),
                now=NOW,
            )

    async def test_not_proposed_is_a_409(self) -> None:
        repo, store, rule_set, _ = _world()
        rejected = _proposal(rule_set, status="rejected")
        repo.proposals[rejected.id] = rejected
        with pytest.raises(ProposalStateConflictError, match="not_proposed") as info:
            await approve_proposal(
                _repo(repo),
                store,
                context=_context(),
                proposal_id=rejected.id,
                idempotency_key=KEY,
                body=_approve_body(),
                now=NOW,
            )
        assert info.value.status_code == 409

    async def test_past_expires_at_is_a_409_even_before_the_loop_stamps_expired(self) -> None:
        repo, store, rule_set, _ = _world()
        late = _proposal(rule_set, expires_at=NOW - timedelta(seconds=1))
        repo.proposals[late.id] = late
        with pytest.raises(ProposalStateConflictError, match="expired"):
            await approve_proposal(
                _repo(repo),
                store,
                context=_context(),
                proposal_id=late.id,
                idempotency_key=KEY,
                body=_approve_body(),
                now=NOW,
            )

    async def test_exceeding_max_sol_per_bet_is_a_named_422(self) -> None:
        repo, store, _, proposal = _world()
        with pytest.raises(DeskRefusedError, match="exceeds_max_sol_per_bet") as info:
            await approve_proposal(
                _repo(repo),
                store,
                context=_context(),
                proposal_id=proposal.id,
                idempotency_key=KEY,
                body=_approve_body(size_sol="0.51"),
                now=NOW,
            )
        assert info.value.status_code == 422
        assert repo.proposals[proposal.id].status == "proposed"

    async def test_unknown_proposal_is_a_404(self) -> None:
        repo, store, _, _ = _world()
        with pytest.raises(ProposalNotFoundError):
            await approve_proposal(
                _repo(repo),
                store,
                context=_context(),
                proposal_id=uuid.uuid4(),
                idempotency_key=KEY,
                body=_approve_body(),
                now=NOW,
            )

    async def test_every_post_writes_an_audit_row_with_a_key_hash_never_the_key(self) -> None:
        repo, store, _, proposal = _world()
        sink = InMemoryAuditSink()
        with use_audit_sink(sink):
            await approve_proposal(
                _repo(repo),
                store,
                context=_context(),
                proposal_id=proposal.id,
                idempotency_key=KEY,
                body=_approve_body(),
                now=NOW,
            )
        assert len(sink.events) == 1
        event = sink.events[0]
        assert event.action == "meme_desk.proposal.approved"
        assert event.entity_type == "meme_proposal"
        assert event.entity_id == str(proposal.id)
        assert event.actor_id == str(USER_ID)
        assert event.organization_id == ORG_ID
        assert event.metadata["mode"] == "paper"
        assert "idempotency_key_hash" in event.after
        assert KEY not in str(event.after)


class TestReject:
    async def test_proposed_becomes_rejected_with_the_note(self) -> None:
        repo, store, _, proposal = _world()
        out = await reject_proposal(
            _repo(repo),
            store,
            context=_context(),
            proposal_id=proposal.id,
            idempotency_key=KEY,
            body=RejectProposalIn(note="não gostei"),
            now=NOW,
        )
        assert out.row.status == "rejected"
        assert out.row.decision is not None
        assert out.row.decision.note == "não gostei"
        assert out.row.decision.size_sol is None


class TestManual:
    def _body(self, **overrides: Any) -> ManualProposalIn:
        base: dict[str, Any] = {
            "mint": MINT,
            "size_sol": "0.2",
            "target_x": "2",
            "trailing_pct": "30",
            "max_hold_s": 600,
        }
        base.update(overrides)
        return ManualProposalIn.model_validate(base)

    async def test_files_a_proposal_born_approved_under_operator_1(self) -> None:
        repo, store, rule_set, _ = _world()
        out = await file_manual_proposal(
            _repo(repo),
            store,
            context=_context(),
            idempotency_key=KEY,
            body=self._body(),
            now=NOW,
        )
        row = out.row
        assert row.status == "approved"
        assert row.origin == "operator"
        assert row.reasons == ["operator_manual"]
        assert row.rule_set is not None and row.rule_set.id == rule_set.id
        assert row.decided_by == CLERK_ID
        assert row.expires_at == NOW + timedelta(seconds=120)
        assert row.quote.fee_pct == MANUAL_QUOTE_FEE_PCT
        assert row.quote.cost_sol == Decimal("0.2")
        assert row.quote.fee_sol is not None and row.quote.fee_sol > 0
        assert row.quote.tokens is not None and row.quote.tokens > 0
        assert row.quote.source == "solana_rpc"

    async def test_replay_returns_the_same_proposal(self) -> None:
        repo, store, _, _ = _world()
        first = await file_manual_proposal(
            _repo(repo), store, context=_context(), idempotency_key=KEY, body=self._body(), now=NOW
        )
        second = await file_manual_proposal(
            _repo(repo), store, context=_context(), idempotency_key=KEY, body=self._body(), now=NOW
        )
        assert second.row.id == first.row.id
        assert len(repo.proposals) == 2  # the seeded one + one manual, never two manuals

    async def test_unknown_mint_is_422_mint_unknown(self) -> None:
        repo, store, _, _ = _world()
        with pytest.raises(DeskRefusedError, match="mint_unknown"):
            await file_manual_proposal(
                _repo(repo),
                store,
                context=_context(),
                idempotency_key=KEY,
                body=self._body(mint="Synthetic9NeverSeenxxxxxxxxxxxxxxxxxxxxxxxxx"),
                now=NOW,
            )

    async def test_completed_curve_is_422_curve_completed(self) -> None:
        repo, store, _, _ = _world()
        with pytest.raises(DeskRefusedError, match="curve_completed"):
            await file_manual_proposal(
                _repo(repo),
                store,
                context=_context(),
                idempotency_key=KEY,
                body=self._body(mint=MINT_DONE),
                now=NOW,
            )

    async def test_missing_operator_rule_set_is_422(self) -> None:
        repo, store, _, _ = _world()
        repo.rule_sets.clear()
        with pytest.raises(DeskRefusedError, match="operator_rule_set_missing"):
            await file_manual_proposal(
                _repo(repo),
                store,
                context=_context(),
                idempotency_key=KEY,
                body=self._body(),
                now=NOW,
            )

    async def test_size_above_the_operator_sets_ceiling_is_422(self) -> None:
        repo, store, _, _ = _world()
        with pytest.raises(DeskRefusedError, match="exceeds_max_sol_per_bet"):
            await file_manual_proposal(
                _repo(repo),
                store,
                context=_context(),
                idempotency_key=KEY,
                body=self._body(size_sol="0.6"),
                now=NOW,
            )


class TestSellNow:
    async def test_open_bet_gets_a_sell_now_command(self) -> None:
        repo, store, rule_set, proposal = _world()
        bet = _bet(rule_set, proposal.id)
        repo.bets[bet.id] = bet
        out = await sell_now(
            _repo(repo), store, context=_context(), bet_id=bet.id, idempotency_key=KEY, now=NOW
        )
        assert out.command == "sell_now"
        assert out.bet_id == bet.id
        assert out.proposal_id is None
        assert out.applied_at is None
        assert out.issued_by == CLERK_ID
        assert repo.commands[out.id].command == "sell_now"

    async def test_replay_returns_the_same_command(self) -> None:
        repo, store, rule_set, proposal = _world()
        bet = _bet(rule_set, proposal.id)
        repo.bets[bet.id] = bet
        first = await sell_now(
            _repo(repo), store, context=_context(), bet_id=bet.id, idempotency_key=KEY, now=NOW
        )
        second = await sell_now(
            _repo(repo), store, context=_context(), bet_id=bet.id, idempotency_key=KEY, now=NOW
        )
        assert second.id == first.id
        assert len(repo.commands) == 1

    async def test_second_sell_now_with_another_key_is_409_while_the_first_is_pending(
        self,
    ) -> None:
        repo, store, rule_set, proposal = _world()
        bet = _bet(rule_set, proposal.id)
        repo.bets[bet.id] = bet
        await sell_now(
            _repo(repo), store, context=_context(), bet_id=bet.id, idempotency_key=KEY, now=NOW
        )
        with pytest.raises(BetStateConflictError, match="sell_now_already_pending"):
            await sell_now(
                _repo(repo),
                store,
                context=_context(),
                bet_id=bet.id,
                idempotency_key="desk-key-000002",
                now=NOW,
            )

    async def test_closed_bet_is_409_bet_not_open(self) -> None:
        repo, store, rule_set, proposal = _world()
        bet = _bet(rule_set, proposal.id, status="closed", exit_at=NOW, pnl_sol=Decimal("0.01"))
        repo.bets[bet.id] = bet
        with pytest.raises(BetStateConflictError, match="bet_not_open"):
            await sell_now(
                _repo(repo), store, context=_context(), bet_id=bet.id, idempotency_key=KEY, now=NOW
            )

    async def test_unknown_bet_is_404(self) -> None:
        repo, store, _, _ = _world()
        with pytest.raises(BetNotFoundError):
            await sell_now(
                _repo(repo),
                store,
                context=_context(),
                bet_id=uuid.uuid4(),
                idempotency_key=KEY,
                now=NOW,
            )


class TestCancel:
    async def test_approved_not_yet_filled_gets_a_cancel_command(self) -> None:
        repo, store, rule_set, _ = _world()
        approved = _proposal(rule_set, status="approved")
        repo.proposals[approved.id] = approved
        out = await cancel_proposal(
            _repo(repo),
            store,
            context=_context(),
            proposal_id=approved.id,
            idempotency_key=KEY,
            now=NOW,
        )
        assert out.command == "cancel"
        assert out.proposal_id == approved.id
        assert out.bet_id is None

    async def test_filled_is_409_already_filled(self) -> None:
        repo, store, rule_set, _ = _world()
        filled = _proposal(rule_set, status="filled", bet_id=uuid.uuid4())
        repo.proposals[filled.id] = filled
        with pytest.raises(ProposalStateConflictError, match="already_filled"):
            await cancel_proposal(
                _repo(repo),
                store,
                context=_context(),
                proposal_id=filled.id,
                idempotency_key=KEY,
                now=NOW,
            )

    async def test_rejected_is_409_not_cancellable(self) -> None:
        repo, store, rule_set, _ = _world()
        rejected = _proposal(rule_set, status="rejected")
        repo.proposals[rejected.id] = rejected
        with pytest.raises(ProposalStateConflictError, match="not_cancellable"):
            await cancel_proposal(
                _repo(repo),
                store,
                context=_context(),
                proposal_id=rejected.id,
                idempotency_key=KEY,
                now=NOW,
            )


class TestBodies:
    def test_a_float_amount_is_refused_never_coerced(self) -> None:
        with pytest.raises(ValidationError, match="float"):
            ApproveProposalIn.model_validate(
                {"size_sol": 0.2, "target_x": "2", "trailing_pct": "30", "max_hold_s": 900}
            )

    def test_a_target_at_or_below_1x_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            _approve_body(target_x="1")

    def test_a_trailing_outside_0_100_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            _approve_body(trailing_pct="100")

    def test_an_unknown_field_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            _approve_body(stop="1")


class TestManualQuote:
    def test_no_snapshot_yet_keeps_the_fee_half_real_and_names_the_absence(self) -> None:
        quote = build_manual_quote(None, Decimal("0.2"))
        assert quote["reason"] == "no_snapshot_yet"
        assert quote["price_sol_per_token"] is None
        assert quote["fee_pct"] == "1.75"
        assert Decimal(quote["fee_sol"]) == Decimal("0.2") * Decimal("1.75") / 100

    def test_priced_on_the_snapshot_with_the_curve_arithmetic(self) -> None:
        repo, _, _, _ = _world()
        quote = build_manual_quote(repo.quotes[MINT], Decimal("0.2"))
        assert quote["reason"] is None
        assert quote["source"] == "solana_rpc"
        assert Decimal(quote["cost_sol"]) == Decimal("0.2")
        assert Decimal(quote["tokens"]) > 0
        assert Decimal(quote["price_sol_per_token"]) == Decimal("9.8") / Decimal("1071000000")


class TestDeskCursor:
    def test_round_trip(self) -> None:
        proposal_id = uuid.uuid4()
        cursor = encode_desk_cursor(2, NOW, proposal_id)
        assert decode_desk_cursor(cursor) == (2, NOW, proposal_id)

    def test_none_passes_through(self) -> None:
        assert decode_desk_cursor(None) is None

    def test_garbage_is_a_422(self) -> None:
        with pytest.raises(InvalidDeskCursorError):
            decode_desk_cursor("not-base64!")


class TestLiveMode:
    """T4.14 — ``mode = "live"`` is filed only with the API's own flag; without it
    the refusal is named and **nothing is decided** (the row stays ``proposed``)."""

    async def test_default_mode_is_paper(self) -> None:
        repo, store, _, proposal = _world()
        await approve_proposal(
            _repo(repo),
            store,
            context=_context(),
            proposal_id=proposal.id,
            idempotency_key=KEY,
            body=_approve_body(),
            now=NOW,
        )
        assert repo.proposals[proposal.id].mode == "paper"

    async def test_live_without_the_api_flag_is_refused_by_name_and_decides_nothing(
        self,
    ) -> None:
        repo, store, _, proposal = _world()
        with pytest.raises(DeskRefusedError, match="meme_live_disabled"):
            await approve_proposal(
                _repo(repo),
                store,
                context=_context(),
                proposal_id=proposal.id,
                idempotency_key=KEY,
                body=_approve_body(mode="live"),
                now=NOW,
                live_enabled=False,
            )
        assert repo.decide_calls == 0
        assert repo.proposals[proposal.id].status == "proposed"

    async def test_live_with_the_api_flag_files_the_proposal_for_the_executor(self) -> None:
        repo, store, _, proposal = _world()
        out = await approve_proposal(
            _repo(repo),
            store,
            context=_context(),
            proposal_id=proposal.id,
            idempotency_key=KEY,
            body=_approve_body(mode="live"),
            now=NOW,
            live_enabled=True,
        )
        assert out.row.status == "approved"
        assert repo.proposals[proposal.id].mode == "live"

    async def test_a_manual_live_buy_needs_the_flag_too(self) -> None:
        repo, store, _, _ = _world()
        body = ManualProposalIn.model_validate(
            {
                "mint": MINT,
                "size_sol": "0.2",
                "target_x": "2",
                "trailing_pct": "30",
                "max_hold_s": 600,
                "mode": "live",
            }
        )
        with pytest.raises(DeskRefusedError, match="meme_live_disabled"):
            await file_manual_proposal(
                _repo(repo), store, context=_context(), idempotency_key=KEY, body=body, now=NOW
            )
        assert repo.proposals == {} or all(p.mode == "paper" for p in repo.proposals.values())
        out = await file_manual_proposal(
            _repo(repo),
            store,
            context=_context(),
            idempotency_key=KEY,
            body=body,
            now=NOW,
            live_enabled=True,
        )
        assert out.row.status == "approved"
        assert repo.proposals[out.row.id].mode == "live"
