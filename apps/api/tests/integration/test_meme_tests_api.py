"""``GET /meme/tests``, ``GET /meme/tests.csv`` and ``GET /meme/tests/{bet_id}``
(T4.13) over the real app on Alembic-to-head — testcontainer.

Seeded as ``hunter_worker`` (the loop's role, the only writer of bets): one
closed bet **per exit reason** of the contract's vocabulary, one open bet
with a mark, one manual (operator) bet, one probe with its ``scale`` leg,
one bet on the previous Brasília day (must not appear), a
``meme_features_v3`` minute for one proposal (the Lab's context) and curve
photographs around one bet (the detail's series). Every mint is synthetic
and labelled as such; the rule sets are the ones ``0022``/``0026`` seed.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text

from hunter_api.schemas.meme_desk import ExitReason
from hunter_api.schemas.meme_tests import EXIT_REASON_PT
from hunter_api.services.meme_tests_csv import CSV_COLUMNS
from hunter_core.db.session import role_session
from hunter_core.domain.types import uuid7

from .conftest import create_org

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from .conftest import Actor

pytestmark = pytest.mark.integration

DAY = "2026-09-12"
T0 = datetime(2026, 9, 12, 14, 0, 5, tzinfo=UTC)  # 11:00:05 Brasília
MINT = "SyntheticTestsRecordMintxxxxxxxxxxxxxxxxxxxx"
MINT_MANUAL = "SyntheticTestsRecordManualxxxxxxxxxxxxxxxxxx"
REASONS: tuple[str, ...] = (
    "target",
    "trailing",
    "time_stop",
    "migrated",
    "creator_dump",
    "sell_now",
    "rug_no_snapshot",
    "max_loss",
    "line_broken",
)
FEATURES_END_TIME = T0 - timedelta(seconds=65)


def _j(value: object) -> str:
    return json.dumps(value)


def _entry(sol_spent: str, tokens: str, mcap: str, at: datetime) -> dict[str, Any]:
    return {
        "snapshot": {"observed_at": at.isoformat(), "source": "solana_rpc", "mcap_sol": mcap},
        "decided_at": (at - timedelta(seconds=12)).isoformat(),
        "decision_to_fill_s": 12,
        "fill_delay_snapshots": 1,
        "marginal_price_before_sol": "0.00000003",
        "marginal_price_after_sol": "0.000000031",
        "average_price_sol": "0.0000000305",
        "fee_sol": "0.0035",
        "fee_pct": "1.75",
        "sol_spent": sol_spent,
        "tokens": tokens,
        "sol_usd_source": "coingecko",
    }


def _exit(reason: str, received: str, at: datetime) -> dict[str, Any]:
    if reason == "rug_no_snapshot":
        return {
            "reason": reason,
            "pending_reason": "time_stop",
            "snapshot": None,
            "sol_received": "0",
            "sol_usd_source": None,
        }
    return {
        "reason": reason,
        "snapshot": {"observed_at": at.isoformat(), "source": "solana_rpc", "mcap_sol": "60.1"},
        "sol_received": received,
        "fee_sol": "0.0066",
        "marginal_price_after_sol": "0.000000058",
        "sol_usd_source": "coingecko",
        "trigger": "operator" if reason == "sell_now" else "rules",
    }


@pytest.fixture(scope="module")
def seeded() -> dict[str, Any]:
    return {}


async def _insert_proposal(
    session: AsyncSession,
    *,
    proposal_id: uuid.UUID,
    mint: str,
    rule_set_id: Any,
    origin: str,
    proposed_at: datetime,
    features_end_time: datetime | None,
    reasons: list[str],
) -> None:
    await session.execute(
        text(
            "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, proposed_at, "
            "expires_at, features_end_time, quote, reasons, suggested, decision, decided_by, "
            "decided_at) VALUES (:id, :mint, :rs, :origin, 'approved', :proposed_at, :expires_at, "
            ":fet, CAST(:quote AS jsonb), CAST(:reasons AS jsonb), CAST(:suggested AS jsonb), "
            "CAST(:decision AS jsonb), :decided_by, :decided_at)"
        ),
        {
            "id": proposal_id,
            "mint": mint,
            "rs": rule_set_id,
            "origin": origin,
            "proposed_at": proposed_at,
            "expires_at": proposed_at + timedelta(seconds=120),
            "fet": features_end_time,
            "quote": _j({"source": "solana_rpc", "observed_at": proposed_at.isoformat()}),
            "reasons": _j(reasons),
            "suggested": _j({"size_sol": "0.2"}),
            "decision": _j(
                {"size_sol": "0.2", "target_x": "2", "trailing_pct": "30", "max_hold_s": 900}
            ),
            "decided_by": "rules" if origin == "rules" else "user_FAKE_tests",
            "decided_at": proposed_at + timedelta(seconds=1),
        },
    )


async def _insert_bet(session: AsyncSession, row: dict[str, Any]) -> None:
    await session.execute(
        text(
            "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, mode, status, "
            "entry_at, entry, initial_risk_sol, params, exit_at, exit, pnl_sol, r_multiple, "
            "mark_sol, mark_at, high_water_x, sol_usd_at_entry, sol_usd_at_exit, leg, "
            "parent_bet_id) VALUES (:id, :proposal_id, :rule_set_id, :mint, 'paper', :status, "
            ":entry_at, CAST(:entry AS jsonb), :risk, CAST(:params AS jsonb), :exit_at, "
            "CAST(:exit AS jsonb), :pnl_sol, :r_multiple, :mark_sol, :mark_at, :high_water_x, "
            ":sol_usd_at_entry, :sol_usd_at_exit, :leg, :parent_bet_id)"
        ),
        row,
    )
    await session.execute(
        text("UPDATE meme_proposals SET status = 'filled', bet_id = :bet WHERE id = :id"),
        {"bet": row["id"], "id": row["proposal_id"]},
    )


def _bet_row(
    *,
    bet_id: uuid.UUID,
    proposal_id: uuid.UUID,
    rule_set_id: Any,
    mint: str,
    entry_at: datetime,
    reason: str | None,
    leg: str = "single",
    parent: uuid.UUID | None = None,
    spent: str = "0.2",
) -> dict[str, Any]:
    closed = reason is not None
    received = "0.38" if reason not in {"rug_no_snapshot", "max_loss"} else "0"
    if reason == "max_loss":
        received = "0.1"
    pnl = Decimal(received) - Decimal(spent) if closed else None
    exit_at = entry_at + timedelta(minutes=7, seconds=25) if closed else None
    return {
        "id": bet_id,
        "proposal_id": proposal_id,
        "rule_set_id": rule_set_id,
        "mint": mint,
        "status": "closed" if closed else "open",
        "entry_at": entry_at,
        "entry": _j(_entry(spent, "6443000", "31.5", entry_at)),
        "risk": Decimal(spent),
        "params": _j({"size_sol": spent, "target_x": "2", "trailing_pct": "30", "max_hold_s": 900}),
        "exit_at": exit_at,
        "exit": _j(_exit(reason, received, exit_at)) if closed and exit_at else None,
        "pnl_sol": pnl,
        "r_multiple": (pnl / Decimal(spent)) if pnl is not None else None,
        "mark_sol": Decimal(received) if closed else Decimal("0.25"),
        "mark_at": exit_at if closed else entry_at + timedelta(minutes=3),
        "high_water_x": Decimal("2"),
        "sol_usd_at_entry": Decimal("179"),
        "sol_usd_at_exit": Decimal("181") if closed and reason != "rug_no_snapshot" else None,
        "leg": leg,
        "parent_bet_id": parent,
    }


async def _seed(session: AsyncSession, seeded: dict[str, Any]) -> None:
    rule_sets = {
        name: rs_id
        for name, rs_id in (
            await session.execute(text("SELECT name, id FROM meme_rule_sets WHERE version = '1'"))
        ).all()
    }
    assert {"meme_paper_v0", "operator", "hype_probe_v0"} <= set(rule_sets), rule_sets
    for mint, name in ((MINT, "tests record"), (MINT_MANUAL, "tests manual")):
        await session.execute(
            text(
                "INSERT INTO meme_tokens (mint, name, symbol, first_seen_source, first_seen_at, "
                "last_seen_at, updated_at) VALUES (:mint, :name, 'TST', 'pumpportal_ws', :t, :t, :t)"
            ),
            {"mint": mint, "name": name, "t": T0 - timedelta(minutes=10)},
        )
    bets: dict[str, uuid.UUID] = {}
    # One closed bet per exit reason, entered one minute apart (newest = last reason).
    for index, reason in enumerate(REASONS):
        entry_at = T0 + timedelta(minutes=index)
        proposal_id, bet_id = uuid7(), uuid7()
        await _insert_proposal(
            session,
            proposal_id=proposal_id,
            mint=MINT,
            rule_set_id=rule_sets["meme_paper_v0"],
            origin="rules",
            proposed_at=entry_at - timedelta(seconds=13),
            features_end_time=FEATURES_END_TIME if index == 0 else entry_at - timedelta(minutes=2),
            reasons=["progress_gate", "age_gate"],
        )
        await _insert_bet(
            session,
            _bet_row(
                bet_id=bet_id,
                proposal_id=proposal_id,
                rule_set_id=rule_sets["meme_paper_v0"],
                mint=MINT,
                entry_at=entry_at,
                reason=reason,
            ),
        )
        bets[reason] = bet_id
    # An open bet with a mark.
    open_proposal, open_bet = uuid7(), uuid7()
    await _insert_proposal(
        session,
        proposal_id=open_proposal,
        mint=MINT,
        rule_set_id=rule_sets["meme_paper_v0"],
        origin="rules",
        proposed_at=T0 + timedelta(minutes=20),
        features_end_time=T0 + timedelta(minutes=19),
        reasons=["progress_gate"],
    )
    await _insert_bet(
        session,
        _bet_row(
            bet_id=open_bet,
            proposal_id=open_proposal,
            rule_set_id=rule_sets["meme_paper_v0"],
            mint=MINT,
            entry_at=T0 + timedelta(minutes=20, seconds=13),
            reason=None,
        ),
    )
    bets["open"] = open_bet
    # A manual (operator) bet: no minute, ``operator_manual`` reason.
    manual_proposal, manual_bet = uuid7(), uuid7()
    await _insert_proposal(
        session,
        proposal_id=manual_proposal,
        mint=MINT_MANUAL,
        rule_set_id=rule_sets["operator"],
        origin="operator",
        proposed_at=T0 + timedelta(minutes=30),
        features_end_time=None,
        reasons=["operator_manual"],
    )
    await _insert_bet(
        session,
        _bet_row(
            bet_id=manual_bet,
            proposal_id=manual_proposal,
            rule_set_id=rule_sets["operator"],
            mint=MINT_MANUAL,
            entry_at=T0 + timedelta(minutes=30, seconds=13),
            reason="sell_now",
            spent="0.05",
        ),
    )
    bets["manual"] = manual_bet
    # A probe and its scale leg (0026).
    probe_proposal, probe_bet = uuid7(), uuid7()
    scale_proposal, scale_bet = uuid7(), uuid7()
    for proposal_id, offset in ((probe_proposal, 40), (scale_proposal, 44)):
        await _insert_proposal(
            session,
            proposal_id=proposal_id,
            mint=MINT,
            rule_set_id=rule_sets["hype_probe_v0"],
            origin="rules",
            proposed_at=T0 + timedelta(minutes=offset),
            features_end_time=T0 + timedelta(minutes=offset - 1),
            reasons=["hype_gate"],
        )
    await _insert_bet(
        session,
        _bet_row(
            bet_id=probe_bet,
            proposal_id=probe_proposal,
            rule_set_id=rule_sets["hype_probe_v0"],
            mint=MINT,
            entry_at=T0 + timedelta(minutes=40, seconds=13),
            reason="target",
            leg="probe",
            spent="0.01",
        ),
    )
    await _insert_bet(
        session,
        _bet_row(
            bet_id=scale_bet,
            proposal_id=scale_proposal,
            rule_set_id=rule_sets["hype_probe_v0"],
            mint=MINT,
            entry_at=T0 + timedelta(minutes=44, seconds=13),
            reason="line_broken",
            leg="scale",
            parent=probe_bet,
            spent="0.04",
        ),
    )
    bets["probe"], bets["scale"] = probe_bet, scale_bet
    # Yesterday's bet: entered before 03:00Z of the day -> previous Brasília day.
    old_proposal, old_bet = uuid7(), uuid7()
    await _insert_proposal(
        session,
        proposal_id=old_proposal,
        mint=MINT,
        rule_set_id=rule_sets["meme_paper_v0"],
        origin="rules",
        proposed_at=datetime(2026, 9, 12, 2, 30, tzinfo=UTC),
        features_end_time=datetime(2026, 9, 12, 2, 29, tzinfo=UTC),
        reasons=["progress_gate"],
    )
    await _insert_bet(
        session,
        _bet_row(
            bet_id=old_bet,
            proposal_id=old_proposal,
            rule_set_id=rule_sets["meme_paper_v0"],
            mint=MINT,
            entry_at=datetime(2026, 9, 12, 2, 30, 13, tzinfo=UTC),
            reason="target",
        ),
    )
    bets["yesterday"] = old_bet
    await session.execute(
        text(
            "INSERT INTO meme_features_1m (end_time, mint, features_version, curve_progress_pct, "
            "mcap_sol, unique_buyers_reason, buy_sell_ratio_reason, top10_share_reason, "
            "creator_sold, age_minutes, coverage, computed_at, holders_reason, dev_share_reason, "
            "snipers_reason, tape_reason, creator_net_seller_reason, high_15m_sol, low_15m_sol, "
            "breakout_15m, support_line_sol, support_line_slope, higher_lows, "
            "distance_to_support_pct, line_points, hype_score, hype_reason) VALUES (:end_time, "
            ":mint, 'meme_features_v3', 0.42, 31.2, 'no_trade_feed', 'no_trade_feed', "
            "'no_holders_reader', false, 8, 1, :end_time, 'no_holders_reader', 'no_holders_reader', "
            "'no_holders_reader', 'no_trade_feed', 'no_trade_feed', 33, 25, true, 28.4, 0.1, true, "
            "0.11, 7, 0.7, 'partial')"
        ),
        {"end_time": FEATURES_END_TIME, "mint": MINT},
    )
    await session.execute(
        text(
            "INSERT INTO meme_curve_snapshots (observed_at, mint, source, received_at, "
            "virtual_sol_reserves, virtual_token_reserves, real_sol_reserves, real_token_reserves, "
            "total_supply, complete) VALUES (:at, :mint, 'solana_rpc', :at, :vsr, 1000000000, 1, "
            "700000000, 1000000000, false)"
        ),
        [
            {"at": T0 + timedelta(seconds=offset), "mint": MINT, "vsr": Decimal("30") + offset}
            for offset in (-120, 0, 60, 200, 445, 800)
        ],
    )
    seeded.update(bets)


@pytest.fixture
async def actor(
    client: httpx.AsyncClient,
    make_actor: Callable[[str], Actor],
    session_factory: async_sessionmaker[AsyncSession],
    seeded: dict[str, Any],
) -> Actor:
    owner = await create_org(client, make_actor("tests-record-owner"), "Tests Record Org")
    if not seeded:
        async with role_session(session_factory, db_role="hunter_worker") as session:
            await _seed(session, seeded)
    return owner


def _url(actor: Actor, suffix: str = "") -> str:
    return f"/api/v1/orgs/{actor.org_id}/meme/tests{suffix}"


class TestListTests:
    async def test_one_row_per_bet_of_the_day_with_every_reason_labelled(
        self, client: httpx.AsyncClient, actor: Actor, seeded: dict[str, Any]
    ) -> None:
        response = await client.get(_url(actor), params={"day": DAY}, headers=actor.headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["label"].startswith("Registro de testes")
        assert body["day"] == DAY
        assert body["day_start"] == "2026-09-12T03:00:00Z"
        assert body["sources"]["wallets"] in {"não observada", "observada", "leitura indisponível"}
        assert body["real_items"] == []
        ids = [row["id"] for row in body["items"]]
        assert str(seeded["yesterday"]) not in ids
        assert len(ids) == len(REASONS) + 4  # + open + manual + probe + scale
        # newest entry first
        assert ids[0] == str(seeded["scale"])
        by_id = {row["id"]: row for row in body["items"]}
        for reason in REASONS:
            row = by_id[str(seeded[reason])]
            assert row["exit"]["reason"] == reason
            assert row["exit"]["reason_label"] == EXIT_REASON_PT[reason]
            assert row["exit"]["provisional"] is False
            assert row["duration_s"] == 445
            assert row["entry"]["sol_spent"] == "0.2"
            assert row["entry"]["fill_delay_s"] == 12
            assert row["entry"]["mcap_sol"] == "31.5"
        rug = by_id[str(seeded["rug_no_snapshot"])]
        assert rug["exit"]["pending_reason"] == "time_stop"
        assert rug["pnl_sol"] == "-0.2" and rug["pnl_usd"] is None
        assert rug["pnl_usd_reason"] == "no_exit_quote"
        target = by_id[str(seeded["target"])]
        assert target["pnl_sol"] == "0.18" and target["pnl_usd"] == "32.58"
        assert target["r_multiple"] == "0.9"
        assert target["exit"]["price_sol_per_token"] == "0.000000058"
        assert target["rule_set"]["label"] == "meme_paper_v0/1"
        assert target["token_name"] == "tests record"

    async def test_open_manual_and_legs(
        self, client: httpx.AsyncClient, actor: Actor, seeded: dict[str, Any]
    ) -> None:
        body = (await client.get(_url(actor), params={"day": DAY}, headers=actor.headers)).json()
        by_id = {row["id"]: row for row in body["items"]}
        open_row = by_id[str(seeded["open"])]
        assert open_row["status"] == "open" and open_row["exit"]["provisional"] is True
        assert open_row["exit"]["sol_received"] == "0.25"
        assert open_row["pnl_sol"] == "0.05" and open_row["r_multiple"] == "0.25"
        assert open_row["pnl_usd_basis"] == "entry_quote_provisional"
        assert open_row["exit"]["reason_label"].startswith("aberta")
        manual = by_id[str(seeded["manual"])]
        assert manual["origin"] == "operator"
        assert manual["rule_set"]["label"] == "operator/1"
        assert manual["lab_context"]["reason"] == "manual_no_minute"
        assert manual["lab_context"]["gate_reasons"] == ["operator_manual"]
        scale = by_id[str(seeded["scale"])]
        assert scale["leg"] == "scale" and scale["parent_bet_id"] == str(seeded["probe"])
        assert scale["exit"]["reason_label"] == "linha rompida"
        assert by_id[str(seeded["probe"])]["leg"] == "probe"

    async def test_lab_context_reads_the_v3_minute(
        self, client: httpx.AsyncClient, actor: Actor, seeded: dict[str, Any]
    ) -> None:
        body = (await client.get(_url(actor), params={"day": DAY}, headers=actor.headers)).json()
        by_id = {row["id"]: row for row in body["items"]}
        lab = by_id[str(seeded["target"])]["lab_context"]
        assert lab["reason"] is None and lab["features_version"] == "meme_features_v3"
        assert lab["line_drawn"] is True and lab["support_line_sol"] == "28.4"
        assert lab["hype_score"] == "0.7" and lab["hype_reason"] == "partial"
        assert lab["creator_sold"] is False and lab["curve_progress_pct"] == "0.42"
        assert lab["higher_lows"] is True and lab["breakout_15m"] is True
        other = by_id[str(seeded["trailing"])]["lab_context"]
        assert other["reason"] == "no_features_row" and other["line_drawn"] is None

    async def test_totals_cover_the_whole_day_not_the_page(
        self, client: httpx.AsyncClient, actor: Actor
    ) -> None:
        body = (
            await client.get(_url(actor), params={"day": DAY, "limit": 3}, headers=actor.headers)
        ).json()
        assert len(body["items"]) == 3 and body["next_cursor"]
        totals = body["totals"]
        assert totals["bets"] == len(REASONS) + 4
        assert totals["closed"] == len(REASONS) + 3 and totals["open"] == 1
        # 0.38 - 0.2 = +0.18 for seven reasons, -0.2 rug, -0.1 max_loss, manual +0.33,
        # probe +0.37, scale +0.34
        assert totals["wins"] == 10 and totals["losses"] == 2
        assert Decimal(totals["pnl_sol"]) == Decimal("1.26") + Decimal("0.33") + Decimal(
            "0.37"
        ) + Decimal("0.34") - Decimal("0.3")
        assert Decimal(totals["provisional_pnl_sol"]) == Decimal("0.05")
        assert totals["unpriced_usd"] == 1
        assert set(body["rule_sets"]) == {"hype_probe_v0", "meme_paper_v0", "operator"}

    async def test_keyset_pages_without_overlap_or_gap(
        self, client: httpx.AsyncClient, actor: Actor
    ) -> None:
        seen: list[str] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"day": DAY, "limit": 4}
            if cursor:
                params["cursor"] = cursor
            body = (await client.get(_url(actor), params=params, headers=actor.headers)).json()
            seen.extend(row["id"] for row in body["items"])
            cursor = body["next_cursor"]
            if not cursor:
                break
        assert len(seen) == len(set(seen)) == len(REASONS) + 4

    async def test_rule_set_filter(self, client: httpx.AsyncClient, actor: Actor) -> None:
        body = (
            await client.get(
                _url(actor), params={"day": DAY, "rule_set": "operator"}, headers=actor.headers
            )
        ).json()
        assert [row["rule_set"]["label"] for row in body["items"]] == ["operator/1"]
        assert body["totals"]["bets"] == 1

    async def test_a_day_without_bets_is_empty_not_an_error(
        self, client: httpx.AsyncClient, actor: Actor
    ) -> None:
        body = (
            await client.get(_url(actor), params={"day": "2026-01-01"}, headers=actor.headers)
        ).json()
        assert body["items"] == [] and body["totals"]["bets"] == 0
        assert body["rule_sets"] == []

    async def test_a_bad_cursor_is_422(self, client: httpx.AsyncClient, actor: Actor) -> None:
        response = await client.get(
            _url(actor), params={"day": DAY, "cursor": "nope"}, headers=actor.headers
        )
        assert response.status_code == 422


class TestCsv:
    async def test_byte_exact_for_the_manual_bet(
        self, client: httpx.AsyncClient, actor: Actor, seeded: dict[str, Any]
    ) -> None:
        response = await client.get(
            _url(actor, ".csv"), params={"day": DAY, "rule_set": "operator"}, headers=actor.headers
        )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("text/csv")
        assert response.headers["content-disposition"] == (
            'attachment; filename="testes-meme-2026-09-12.csv"'
        )
        expected_row = (
            f"{seeded['manual']};PAPEL;operator/1;single;tests manual;TST;{MINT_MANUAL};fechada;"
            "12/09/2026 11:30:18;0,00000003;31,5;0,05;6443000;0,0035;12;"
            "12/09/2026 11:37:43;não;0,000000058;60,1;0,38;0,0066;vender agora (operador);445;"
            "0,33;59,73;exit_quote;179;181;coingecko;6,6;"
            ";;;;;;;operator_manual;"
        )
        expected = (
            b"\xef\xbb\xbf" + (";".join(CSV_COLUMNS) + "\r\n" + expected_row + "\r\n").encode()
        )
        assert response.content == expected

    async def test_the_whole_day_has_one_line_per_bet(
        self, client: httpx.AsyncClient, actor: Actor
    ) -> None:
        response = await client.get(_url(actor, ".csv"), params={"day": DAY}, headers=actor.headers)
        lines = response.content.decode("utf-8-sig").split("\r\n")
        assert lines[0].startswith("id;tipo;conjunto")
        assert len([line for line in lines[1:] if line]) == len(REASONS) + 4
        assert "rug — sem fotografia" in response.content.decode("utf-8")


class TestDetail:
    async def test_the_curve_runs_from_entry_to_exit_with_a_margin(
        self, client: httpx.AsyncClient, actor: Actor, seeded: dict[str, Any]
    ) -> None:
        response = await client.get(_url(actor, f"/{seeded['target']}"), headers=actor.headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["row"]["id"] == str(seeded["target"])
        assert body["row"]["lab_context"]["features_version"] == "meme_features_v3"
        assert body["curve_from"] == "2026-09-12T13:55:05Z"
        assert body["curve_to"] == "2026-09-12T14:12:30Z"
        observed = [point["observed_at"] for point in body["curve"]]
        # -120 s, 0, +60 s, +200 s, +445 s are inside; +800 s is past exit + 5 min
        assert observed == [
            "2026-09-12T13:58:05Z",
            "2026-09-12T14:00:05Z",
            "2026-09-12T14:01:05Z",
            "2026-09-12T14:03:25Z",
            "2026-09-12T14:07:30Z",
        ]
        assert all(point["mcap_sol"] is not None for point in body["curve"])

    async def test_unknown_bet_is_404(self, client: httpx.AsyncClient, actor: Actor) -> None:
        response = await client.get(_url(actor, f"/{uuid.uuid4()}"), headers=actor.headers)
        assert response.status_code == 404
        assert response.json()["type"].endswith("meme-bet-not-found")


def test_every_exit_reason_is_seeded_once() -> None:
    """The fixture above must keep pace with the contract's vocabulary."""
    from typing import get_args

    assert set(REASONS) == set(get_args(ExitReason))
