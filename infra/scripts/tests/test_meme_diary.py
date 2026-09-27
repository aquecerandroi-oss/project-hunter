# pyright: reportPrivateUsage=false
# (the ``_rule_set_day`` regression tests dispatch on the module's private SQL
# statement objects by identity, on purpose — see ``_RuleSetDaySession`` below)
"""``infra/scripts/meme_diary_render.py`` and the pure helpers of ``meme_diary.py``
— no database: the note is a function of the rows.

Run: ``uv run pytest infra/scripts/tests/test_meme_diary.py -q``
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import meme_diary  # noqa: E402
from meme_diary import day_bounds, max_drawdown  # noqa: E402
from meme_diary_render import (  # noqa: E402
    BetLine,
    DiaryInputs,
    RuleSetDay,
    render_diary,
    required_daily_return,
)

pytestmark = pytest.mark.unit

DAY = date(2026, 9, 12)


def _rule_set(**overrides: object) -> RuleSetDay:
    base: dict[str, object] = {
        "name": "meme_paper_v0",
        "version": "1",
        "kind": "research_only",
        "exp_ref": "EXP-M1",
        "wallet_max_sol": Decimal("2.0"),
        "balance_start_sol": Decimal("2.0"),
        "balance_end_sol": Decimal("2.03"),
        "realized_day_sol": Decimal("0.03"),
        "realized_total_sol": Decimal("0.03"),
        "r_day": Decimal("0.6"),
        "r_total": Decimal("0.6"),
        "drawdown_day_sol": Decimal("0.02"),
        "drawdown_total_sol": Decimal("0.02"),
        "bets_day": 2,
        "closed_day": 2,
        "wins_day": 1,
        "rugs_day": 0,
    }
    base.update(overrides)
    return RuleSetDay(**base)  # type: ignore[arg-type]


def _inputs(**overrides: object) -> DiaryInputs:
    base: dict[str, object] = {
        "day": DAY,
        "generated_at": datetime(2026, 9, 12, 21, 0, tzinfo=UTC),
        "rule_sets": [_rule_set()],
        "bets": [
            BetLine(
                mint="5bmYxJJnvAKn23VMxvjiTfeBckEmMok7C3SxztaA9c38",
                rule_set="meme_paper_v0/1",
                exp_ref="EXP-M1",
                entry_at=datetime(2026, 9, 12, 12, 0, tzinfo=UTC),
                exit_at=datetime(2026, 9, 12, 12, 5, tzinfo=UTC),
                exit_reason="target",
                r_multiple=Decimal("1.1"),
                pnl_sol=Decimal("0.055"),
                pnl_usd=Decimal("5.58"),
                sol_usd_source="pumpfun_rest:/sol-price",
                sol_usd_observed_at="2026-09-12T12:05:00+00:00",
                initial_risk_sol=Decimal("0.05"),
            )
        ],
        "unfilled_by_refusal": {"no_later_snapshot": 1},
        "expired_proposals": 0,
        "gaps_by_stream_reason": {},
        "sol_usd": Decimal("101.4445"),
        "sol_usd_source": "pumpfun_rest:/sol-price",
        "sol_usd_observed_at": "2026-09-12T12:05:00+00:00",
        "clock_start": DAY,
        "lab_last_tick_at": datetime(2026, 9, 12, 20, 59, tzinfo=UTC),
    }
    base.update(overrides)
    return DiaryInputs(**base)  # type: ignore[arg-type]


def test_the_note_has_the_frontmatter_and_the_six_sections_in_order() -> None:
    note = render_diary(_inputs())
    assert note.startswith(
        "---\ntags: [operacoes, diario, meme, m4]\nstatus: registro\nowner: sexta-feira\nupdated: 2026-09-12\n---\n"
    )
    positions = [note.index(f"## {n}.") for n in range(1, 7)]
    assert positions == sorted(positions)
    assert "PAPEL — nenhuma transação real" in note
    assert "09:00:00 | 09:05:00 | target | 1.1 | 0.055 | 5.58 | pumpfun_rest:/sol-price @" in note
    assert "Retorno diário exigido:" in note and "%/dia com 30 dias restantes" in note
    assert "Retorno diário medido: 1.5 %/dia" in note  # 0.03 / (2.03 − 0.03)
    assert "`no_later_snapshot`: 1" in note
    assert "último tick às 2026-09-12 17:59:00 BRT" in note
    assert note.rstrip().endswith("(a preencher pelo arquivista — Sexta-feira)")


def test_a_number_nobody_observed_is_a_dash_with_a_reason_never_zero() -> None:
    note = render_diary(
        _inputs(
            bets=[],
            rule_sets=[_rule_set(r_day=None, drawdown_day_sol=None, closed_day=0, bets_day=0)],
            sol_usd=None,
            sol_usd_source=None,
            sol_usd_observed_at=None,
            lab_last_tick_at=None,
        )
    )
    assert "Nenhuma aposta aberta neste dia" in note
    assert "— (sem fechada)" in note
    assert "— (sem cotação SOL/USD observada)" in note
    assert "— (nenhuma aposta fechada no dia)" in note
    assert "laço parado ou nunca rodou" in note
    assert "| 0 |" not in note.split("## 4.")[1].split("## 5.")[0]


def test_the_goal_formula_is_the_decision_notes() -> None:
    rate = required_daily_return(Decimal(20_000), 30)
    assert rate is not None and abs(rate - Decimal("0.21563")) < Decimal("0.0001")
    assert required_daily_return(Decimal(0), 30) is None
    assert required_daily_return(Decimal(20_000), 0) is None


def test_the_day_is_brasilia_and_the_drawdown_is_the_deepest_fall() -> None:
    start, end = day_bounds(DAY)
    assert start.astimezone(UTC) == datetime(2026, 9, 12, 3, 0, tzinfo=UTC)
    assert (end - start).days == 1
    assert max_drawdown([]) is None
    assert max_drawdown(
        [Decimal("0.1"), Decimal("-0.05"), Decimal("-0.1"), Decimal("0.3")]
    ) == Decimal("0.15")
    assert max_drawdown([Decimal("-0.02")]) == Decimal("0.02"), "a first loss counts from zero"


def test_the_real_observed_section_is_labelled_and_reads_the_labs_verdict() -> None:
    """T4.12: section 2b sits between 2 and 3, carries the REAL label, and a buy's
    line says what every gate said — read from ``lab_context``, never invented."""
    from meme_diary_render import WalletTradeLine
    from meme_diary_wallets import lab_verdicts_of

    context: dict[str, Any] = {
        "reason": None,
        "rule_sets": {
            "meme_paper_v0/1": {"accepted": False, "refusals": ["creator_net_seller_unknown"]},
            "hype_probe_v0/1": {"accepted": True, "refusals": []},
            "trendline_v0/1": {"accepted": None, "refusals": []},
        },
    }
    assert lab_verdicts_of(context) == {
        "meme_paper_v0/1": "creator_net_seller_unknown",
        "hype_probe_v0/1": "aceito",
        "trendline_v0/1": "sem linha de features",
    }
    assert lab_verdicts_of(None) == {} and lab_verdicts_of({"reason": "no_features_row"}) == {}
    buy = WalletTradeLine(
        wallet="6nAh8drzAYfFZuTFFRgwRdV8tNndFiX1E8NGRAGzSk5F",
        mint="5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump",
        side="buy",
        venue="curve",
        block_time=datetime(2026, 9, 12, 16, 14, 9, tzinfo=UTC),
        sol_total=Decimal("0.9900885"),
        token_amount=Decimal("22628881.309131"),
        reason=None,
        lab_verdicts=lab_verdicts_of(context),
        position_status="open",
        realized_pnl_sol=Decimal(0),
        r_multiple=None,
    )
    ghost = WalletTradeLine(
        wallet=buy.wallet,
        mint=None,
        side="unknown",
        venue=None,
        block_time=None,
        sol_total=None,
        token_amount=None,
        reason="transaction_not_found",
        lab_verdicts={},
        position_status=None,
        realized_pnl_sol=None,
        r_multiple=None,
    )
    note = render_diary(_inputs(real_observed=[buy, ghost]))
    section = note.split("## 2b.")[1].split("## 3.")[0]
    assert note.index("## 2.") < note.index("## 2b.") < note.index("## 3.")
    assert "REAL — observado na cadeia, não executado por este sistema" in section
    assert (
        "| `6nAh8drz` | `5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump` | compra | curve | 13:14:09 | 0.990088 | 22628881.31 | open | 0 |"
        in section
    )
    assert (
        "`hype_probe_v0/1`: aceito" in section
        and "`meme_paper_v0/1`: creator_net_seller_unknown" in section
    )
    assert "desconhecido (transaction_not_found)" in section and "— (não decodificado)" in section
    empty = render_diary(_inputs())
    assert "Nenhuma operação real observada neste dia" in empty


# --- T4.98: a rule set without a declared wallet ceiling must not crash the close ---
#
# ``launch_v0`` version ``1`` (retired 2026-09-19) has no ``wallet_max_sol`` key in
# its params — it sizes per bet instead of from a wallet ceiling. ``_rule_set_day``
# indexed ``params["wallet_max_sol"]`` directly and raised ``KeyError`` for every
# night since, because ``_RULE_SETS`` selects every row regardless of status.

LAUNCH_V0_PARAMS: dict[str, object] = {
    "clock": "event",
    "exit_key": "lancamento_6s_ou_primeiro_sell",
    "size_sol": "0.01",
    "time_stop_s": 6,
    "max_creator_initial_sol": "2",
    "max_drawdown_from_peak_pct": "20",
    "exit_on_first_third_party_sell": True,
}


class _FakeMappingRows(list[Any]):
    def all(self) -> list[Any]:
        return list(self)

    def one(self) -> Any:
        return self[0]

    def first(self) -> Any:
        return self[0] if self else None


class _FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def mappings(self) -> _FakeMappingRows:
        return _FakeMappingRows(self._rows)

    def scalars(self) -> list[Any]:
        return list(self._rows)


class _RuleSetDaySession:
    """Answers the queries ``_rule_set_day`` makes, by statement identity — no DB."""

    async def execute(self, stmt: object, params: object = None) -> _FakeResult:
        if stmt is meme_diary._WALLET_AT:
            return _FakeResult([{"realized": Decimal(0), "exposure": Decimal(0)}])
        if stmt is meme_diary._DAY_STATS:
            return _FakeResult([{"bets": 0, "closed": 0, "wins": 0, "rugs": 0, "r_day": None}])
        if stmt is meme_diary._CLOSED_SERIES:
            return _FakeResult([])
        if stmt is meme_diary._OPEN_AT:
            return _FakeResult([])
        raise AssertionError(f"unexpected statement: {stmt!r}")

    async def scalar(self, stmt: object, params: object = None) -> Any:
        if stmt is meme_diary._R_TOTAL:
            return None
        raise AssertionError(f"unexpected scalar statement: {stmt!r}")


def _rule_row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "11111111-1111-1111-1111-111111111111",
        "name": "meme_paper_v0",
        "version": "1",
        "kind": "research_only",
        "exp_ref": "EXP-M1",
        "params": {"wallet_max_sol": "2.0"},
    }
    base.update(overrides)
    return base


def test_rule_set_day_reads_an_absent_wallet_ceiling_as_none_not_a_crash() -> None:
    day_start, day_end = day_bounds(DAY)
    row = _rule_row(name="launch_v0", exp_ref=None, params=LAUNCH_V0_PARAMS)
    result = asyncio.run(
        meme_diary._rule_set_day(_RuleSetDaySession(), row, day_start=day_start, day_end=day_end)
    )
    assert result.wallet_max_sol is None
    assert result.balance_start_sol is None
    assert result.balance_end_sol is None


def test_rule_set_day_still_reads_a_declared_wallet_ceiling() -> None:
    day_start, day_end = day_bounds(DAY)
    result = asyncio.run(
        meme_diary._rule_set_day(
            _RuleSetDaySession(), _rule_row(), day_start=day_start, day_end=day_end
        )
    )
    assert result.wallet_max_sol == Decimal("2.0")
    assert result.balance_start_sol == Decimal("2.0")
    assert result.balance_end_sol == Decimal("2.0")


def test_a_rule_set_without_a_declared_wallet_ceiling_renders_honestly() -> None:
    """The teto cell reads the honest reason, never a fabricated zero ceiling."""
    note = render_diary(
        _inputs(
            rule_sets=[
                _rule_set(
                    name="launch_v0",
                    exp_ref=None,
                    wallet_max_sol=None,
                    balance_start_sol=None,
                    balance_end_sol=None,
                )
            ]
        )
    )
    section = note.split("## 1.")[1].split("## 2.")[0]
    assert "| `launch_v0/1` | research_only | — (sem teto declarado) |" in section
    row = [line for line in section.splitlines() if line.startswith("| `launch_v0/1`")][0]
    assert row.count("— (sem teto declarado)") == 3, row
    assert "sem leitura" not in row, "no wallet ceiling is a structural absence, not a failed read"


# --- T4.98 round 2: capital incompleto never mixes populations (Astra HIGH) ---


def test_the_goal_omits_the_number_when_capital_is_incomplete() -> None:
    """Astra's reproduced scenario: ``launch_v0/1`` has no declared ceiling and
    closes +0,50 SOL on the day; ``flow_v2/1`` has a 2,0 SOL ceiling and zero PnL.
    Publishing capital 2 SOL and a 33,33 %/dia measured return mixes a population
    with a known balance and one without — an invented number (CLAUDE.md)."""
    note = render_diary(
        _inputs(
            rule_sets=[
                _rule_set(
                    name="flow_v2",
                    version="1",
                    exp_ref=None,
                    wallet_max_sol=Decimal("2.0"),
                    balance_start_sol=Decimal("2.0"),
                    balance_end_sol=Decimal("2.0"),
                    realized_day_sol=Decimal("0"),
                    closed_day=1,
                ),
                _rule_set(
                    name="launch_v0",
                    version="1",
                    exp_ref=None,
                    wallet_max_sol=None,
                    balance_start_sol=None,
                    balance_end_sol=None,
                    realized_day_sol=Decimal("0.50"),
                    closed_day=1,
                ),
            ]
        )
    )
    section = note.split("## 4.")[1].split("## 5.")[0]
    assert "— (capital incompleto: 1 conjunto(s) sem teto declarado: `launch_v0/1`)" in section, (
        section
    )
    assert section.count("— (capital incompleto)") == 2  # exigido e medido
    assert "33.33" not in section and "33,33" not in section
    assert "2 SOL" not in section and "2.0 SOL" not in section


def test_the_goal_never_publishes_zero_capital_when_every_set_lacks_a_ceiling() -> None:
    note = render_diary(
        _inputs(
            rule_sets=[
                _rule_set(
                    name="launch_v0",
                    version="1",
                    exp_ref=None,
                    wallet_max_sol=None,
                    balance_start_sol=None,
                    balance_end_sol=None,
                )
            ]
        )
    )
    section = note.split("## 4.")[1].split("## 5.")[0]
    assert "0 SOL" not in section
    assert "— (capital incompleto: 1 conjunto(s) sem teto declarado: `launch_v0/1`)" in section, (
        section
    )
    assert "Retorno diário exigido: — (capital incompleto)" in section
    assert "Retorno diário medido: — (capital incompleto)" in section


def test_the_goal_section_is_unchanged_when_every_rule_set_has_a_ceiling() -> None:
    """Pins section 4 byte-for-byte for the all-known-capital case — a regression
    here would silently change every already-recovered diary page."""
    note = render_diary(_inputs())
    section = note.split("## 4.")[1].split("## 5.")[0]
    assert section == (
        " Distância à meta\n\n"
        "> [!alerta] Conta sobre o alvo declarado (US$ 7 M em 30 dias), nunca previsão de retorno.\n\n"
        "- Capital (paper, soma dos conjuntos ativos ao fechar o dia): 2.03 SOL = "
        "US$ 205.93 (SOL/USD 101.4445, pumpfun_rest:/sol-price @ 2026-09-12T12:05:00+00:00)\n"
        "- Retorno diário exigido: 41.59 %/dia com 30 dias restantes\n"
        "- Retorno diário medido: 1.5 %/dia\n"
        "- Início do relógio: 2026-09-12 (primeiro conjunto ativo; seed da migração 0022)\n\n"
    )
