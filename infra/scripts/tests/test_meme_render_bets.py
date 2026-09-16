"""T4.25 — o gráfico de uma aposta meme não pode ver o futuro dela.

Roda sem rede e sem banco: a fixture é **sintética** (três apostas construídas
aqui, com números escolhidos para que cada asserção tenha um valor esperado
conhecido) no formato exato que ``meme_render_bets.py export`` grava.

    uv run --with matplotlib pytest infra/scripts/tests/test_meme_render_bets.py -q

Sem matplotlib os testes de desenho são pulados (``importorskip``) e os de
geometria, nome de arquivo e notas continuam valendo — matplotlib não está no
`pyproject.toml` desta árvore (T3.34) e o CI não o instala.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import meme_render_bets_notes as notes_mod  # noqa: E402
from meme_render_bets_model import (  # noqa: E402
    Bet,
    load_bets,
    minute_at,
    previous_high,
    rule_set_slug,
    support_segment,
)

DAY = "2026-09-14"
ENTRY_A = datetime(2026, 9, 14, 5, 2, 35, tzinfo=UTC)
"""02:02:35 BRT — o fuso é o de Brasília em toda a página e todo nome de arquivo."""
EXIT_A = datetime(2026, 9, 14, 5, 12, 51, tzinfo=UTC)
ENTRY_MINUTE = datetime(2026, 9, 14, 5, 2, tzinfo=UTC)
FLOW_PARAMS = {
    "size_sol": "0.05",
    "target_x": "3",
    "trailing_pct": "35",
    "trailing_arm_x": "1.5",
    "max_hold_s": 1800,
    "max_loss_pct": "50",
    "exit_on_line_break": True,
    "clock": "15s",
}
LINE_PARAMS = {
    "size_sol": "0.05",
    "target_x": "2",
    "trailing_pct": "30",
    "max_hold_s": 900,
    "max_loss_pct": "50",
    "exit_on_line_break": True,
    "clock": "1m",
}


def minute(
    end: datetime,
    mcap: str | None,
    *,
    support: str | None = None,
    slope: str | None = None,
    high: str | None = None,
    breakout: bool | None = None,
    higher: bool | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    return {
        "end_time": end.isoformat(),
        "mcap_sol": mcap,
        "support_line_sol": support,
        "support_line_slope": slope,
        "high_15m_sol": high,
        "low_15m_sol": None if high is None else "95",
        "breakout_15m": breakout,
        "higher_lows": higher,
        "line_reason": reason,
    }


PEAK_A = ENTRY_A + timedelta(minutes=3)


def _path_a(at: datetime) -> str:
    """A sóbria: sobe até a entrada, faz o pico em +3 min, morre na saída.

    Uma só função para a série de 15 s e para as fotografias, porque as duas
    olham a mesma curva — uma fixture em que elas discordam desenharia um
    gráfico que nenhum mercado produziu.
    """

    def between(t0: datetime, t1: datetime, y0: float, y1: float) -> float:
        share = (at - t0).total_seconds() / (t1 - t0).total_seconds()
        return y0 + (y1 - y0) * min(max(share, 0.0), 1.0)

    if at <= ENTRY_A:
        value = between(ENTRY_A - timedelta(minutes=8), ENTRY_A, 100.0, 120.5)
    elif at <= PEAK_A:
        value = between(ENTRY_A, PEAK_A, 120.5, 128.0)
    else:
        value = between(PEAK_A, EXIT_A, 128.0, 104.25)
    return f"{value:.2f}"


def bet_with_line() -> dict[str, Any]:
    """`flow_v2/2`, WIF: linha traçada, rompimento, venda do criador, `line_broken`."""
    fast_start = ENTRY_A - timedelta(minutes=5)
    fast = [
        [
            (fast_start + timedelta(seconds=15 * i)).isoformat(),
            _path_a(fast_start + timedelta(seconds=15 * i)),
        ]
        for i in range(int((EXIT_A + timedelta(minutes=5) - fast_start).total_seconds()) // 15)
    ]
    snap_start = ENTRY_A - timedelta(minutes=8)
    snapshots = [
        [
            (snap_start + timedelta(minutes=i)).isoformat(),
            "pumpfun_rest",
            _path_a(snap_start + timedelta(minutes=i)),
            False,
        ]
        for i in range(24)
    ]
    return {
        "day": DAY,
        "bet_id": "bet-a",
        "rule_set": "flow_v2/2",
        "kind": "research_only",
        "exp_ref": "EXP-M5",
        "code_ref": "hunter_indicators.meme.rules@sha256:aaaa",
        "rule_set_params": FLOW_PARAMS,
        "params": FLOW_PARAMS,
        "mint": "5zEJv98Gen7Rv6MhvzPr83cbkE4Wawy74STVDVhMpump",
        "symbol": "WIF",
        "leg": "single",
        "outcome_quality": "measured",
        "outcome_quality_reason": None,
        "entry_at": ENTRY_A.isoformat(),
        "exit_at": EXIT_A.isoformat(),
        "entry_mcap_sol": "120.5",
        "exit_mcap_sol": "104.25",
        "exit_reason": "line_broken",
        "r_multiple": "-0.0403",
        "pnl_sol": "-0.002013",
        "initial_risk_sol": "0.05",
        "high_water_x": "1.08",
        "creator_sold_seen_at": (ENTRY_A + timedelta(minutes=6)).isoformat(),
        "creator_sold_fraction": "0.83",
        "manual_plan": None,
        "features_15s": fast,
        "features_1m": [
            minute(
                ENTRY_MINUTE - timedelta(minutes=2),
                "110",
                support="100",
                slope="2",
                high="118",
                breakout=False,
                higher=True,
            ),
            minute(
                ENTRY_MINUTE - timedelta(minutes=1),
                "115",
                support="102",
                slope="2",
                high="119",
                breakout=False,
                higher=True,
            ),
            minute(
                ENTRY_MINUTE,
                "120.5",
                support="104",
                slope="2",
                high="121",
                breakout=True,
                higher=True,
            ),
            minute(
                ENTRY_MINUTE + timedelta(minutes=1),
                "118",
                support="106",
                slope="2",
                high="121",
                breakout=False,
                higher=True,
            ),
            minute(
                ENTRY_MINUTE + timedelta(minutes=8),
                "104",
                support="110",
                slope="2",
                high="121",
                breakout=False,
                higher=True,
            ),
        ],
        "snapshots": snapshots,
    }


def bet_without_line() -> dict[str, Any]:
    """`trendline_v0/1`, BONK: sem linha (`too_few_points`), sem criador, alvo."""
    entry = datetime(2026, 9, 14, 9, 31, 10, tzinfo=UTC)
    exit_at = datetime(2026, 9, 14, 9, 44, 2, tzinfo=UTC)
    minutes = [
        minute(
            entry.replace(second=0) + timedelta(minutes=i),
            str(200 + 20 * i),
            reason="too_few_points",
        )
        for i in range(-2, 13)
    ]
    return {
        "day": DAY,
        "bet_id": "bet-b",
        "rule_set": "trendline_v0/1",
        "kind": "research_only",
        "exp_ref": "EXP-M2",
        "code_ref": "hunter_indicators.meme.rules@sha256:bbbb",
        "rule_set_params": LINE_PARAMS,
        "params": LINE_PARAMS,
        "mint": "GJ1UcM2YSrMnmR2fyFBFy9iVrrGMLvvBUKytARP9pump",
        "symbol": "BONK",
        "leg": "single",
        "outcome_quality": "measured",
        "outcome_quality_reason": None,
        "entry_at": entry.isoformat(),
        "exit_at": exit_at.isoformat(),
        "entry_mcap_sol": "200",
        "exit_mcap_sol": "420",
        "exit_reason": "target",
        "r_multiple": "2.1500",
        "pnl_sol": "0.1075",
        "initial_risk_sol": "0.05",
        "high_water_x": "2.2",
        "creator_sold_seen_at": None,
        "creator_sold_fraction": None,
        "manual_plan": None,
        "features_15s": [],
        "features_1m": minutes,
        "snapshots": [
            [(entry + timedelta(minutes=i)).isoformat(), "pumpfun_rest", str(200 + 20 * i), False]
            for i in range(-2, 13)
        ],
    }


def bet_indeterminate() -> dict[str, Any]:
    """`flow_v2/2`, PEPE: fecho sem fotografia — −1 R na linha, medição nenhuma."""
    entry = datetime(2026, 9, 14, 5, 40, tzinfo=UTC)
    return {
        **bet_with_line(),
        "bet_id": "bet-c",
        "mint": "PH84sm35uJ2osktXUiwpjqdcx9jvPzz32RbFcGupump",
        "symbol": "PEPE",
        "entry_at": entry.isoformat(),
        "exit_at": (entry + timedelta(minutes=4)).isoformat(),
        "entry_mcap_sol": "120.5",
        "exit_mcap_sol": None,
        "exit_reason": "rug_no_snapshot",
        "outcome_quality": "indeterminate",
        "outcome_quality_reason": "no_snapshot_in_window",
        "r_multiple": "-1",
        "creator_sold_seen_at": None,
        "creator_sold_fraction": None,
        "features_15s": [],
        "features_1m": [
            minute(entry.replace(second=0) + timedelta(minutes=i), value, reason="no_snapshot")
            for i, value in ((-2, "118"), (-1, "119"), (0, "120.5"), (1, "96"))
        ],
        "snapshots": [
            [(entry + timedelta(minutes=i)).isoformat(), "pumpfun_rest", value, False]
            for i, value in ((-2, "118"), (-1, "119"), (0, "120.5"), (1, "96"))
        ],
    }


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> Path:
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8"
    )
    return path


@pytest.fixture
def bets(tmp_path: Path) -> list[Bet]:
    jsonl = write_jsonl(
        tmp_path / "day.jsonl", [bet_with_line(), bet_without_line(), bet_indeterminate()]
    )
    return load_bets(jsonl)


def test_the_fixture_is_the_day_it_claims_to_be(bets: list[Bet]) -> None:
    a, b, c = bets
    assert [x.rule_set for x in bets] == ["flow_v2/2", "trendline_v0/1", "flow_v2/2"]
    assert a.ticker == "WIF" and a.entry_brt.hour == 2 and a.entry_brt.minute == 2
    assert a.filename() == "0202-WIF--0.04.png", "02:02 BRT, WIF, R arredondado a 2 casas"
    assert b.filename() == "0631-BONK-+2.15.png"
    assert c.filename() == "0240-PEPE--1.00.png"
    assert a.series()[0] == "15s", "a série de 15 s existe: é ela que desenha"
    assert b.series()[0] == "1m", "sem série de 15 s, o minuto"
    assert a.measured is True and c.measured is False
    assert rule_set_slug(a.rule_set) == "flow_v2-2"
    assert a.r_text == "-0.0403" and b.r_text == "+2.15" and c.r_text == "-1.00"


def test_the_support_line_is_the_screens_geometry_digit_for_digit(bets: list[Bet]) -> None:
    """``y(t) = support + slope × (t − end_time)/1 min`` — ``meme-lines.ts``."""
    entry_minute = minute_at(bets[0].minutes, bets[0].entry_at)
    assert entry_minute is not None and entry_minute.end_time == ENTRY_MINUTE
    assert entry_minute.support_line_sol == Decimal("104")
    span = (ENTRY_MINUTE - timedelta(minutes=15), ENTRY_MINUTE + timedelta(minutes=5))
    segment = support_segment(entry_minute, span)
    assert segment is not None
    assert segment.x1 == span[0] and segment.x2 == span[1]
    assert segment.y1 == Decimal("74"), "104 − 2 × 15 min"
    assert segment.y2 == Decimal("114"), "104 + 2 × 5 min"


def test_the_support_line_never_starts_before_the_drawn_window(bets: list[Bet]) -> None:
    entry_minute = minute_at(bets[0].minutes, bets[0].entry_at)
    assert entry_minute is not None
    span = (ENTRY_MINUTE - timedelta(minutes=2), ENTRY_MINUTE + timedelta(minutes=5))
    segment = support_segment(entry_minute, span)
    assert segment is not None and segment.x1 == span[0]
    assert segment.y1 == Decimal("100"), "104 − 2 × 2 min: a reta é cortada, não estendida"


def test_a_minute_without_a_line_draws_none_and_says_why(bets: list[Bet]) -> None:
    entry_minute = minute_at(bets[1].minutes, bets[1].entry_at)
    assert entry_minute is not None and entry_minute.support_line_sol is None
    assert entry_minute.line_reason == "too_few_points"
    assert support_segment(entry_minute, bets[1].line_span) is None
    assert previous_high(bets[1].minutes, entry_minute, bets[1].line_span) is None


def test_the_15m_high_is_the_previous_minutes_high_not_this_ones(bets: list[Bet]) -> None:
    """O contrato exclui o próprio minuto: 119 (minuto anterior), nunca 121."""
    entry_minute = minute_at(bets[0].minutes, bets[0].entry_at)
    assert entry_minute is not None
    span = bets[0].line_span
    high = previous_high(bets[0].minutes, entry_minute, span)
    assert high is not None
    assert high.y1 == Decimal("119") == high.y2, "a máxima do minuto anterior, não a deste"
    # A janela daquele minuto começa às 04:46; a janela desenhada só em
    # 04:52:35 (entrada − 10 min), e é ela que corta.
    assert ENTRY_MINUTE - timedelta(minutes=16) < span[0]
    assert high.x1 == span[0], "a reta é cortada pela janela desenhada, nunca estendida"
    assert high.x2 == span[1] == bets[0].exit_at, "projetada até a saída, nunca além dela"


def _tamper_after_the_entry(record: dict[str, Any]) -> dict[str, Any]:
    """Os minutos **posteriores** à entrada, violentamente alterados."""
    entry = datetime.fromisoformat(record["entry_at"])
    minutes: list[dict[str, Any]] = []
    for row in record["features_1m"]:
        if datetime.fromisoformat(row["end_time"]) > entry:
            row = {
                **row,
                "support_line_sol": "999",
                "support_line_slope": "-50",
                "high_15m_sol": "999",
                "mcap_sol": "999",
                "breakout_15m": True,
            }
        minutes.append(row)
    return {**record, "features_1m": minutes}


def test_a_minute_after_the_entry_cannot_move_the_line_that_is_drawn(tmp_path: Path) -> None:
    """Não-antecipação, com a trapaça que prova que a afirmação tem dentes.

    Alterar todos os minutos posteriores à entrada não pode mudar nem a reta de
    suporte nem a máxima de 15 min desenhadas: as duas são lidas no **minuto
    fechado da entrada** e no anterior a ele. A mesma alteração, lida por quem
    usa o **último** minuto — a trapaça deliberada —, muda as duas.
    """
    honest = load_bets(write_jsonl(tmp_path / "a.jsonl", [bet_with_line()]))[0]
    tampered = load_bets(
        write_jsonl(tmp_path / "b.jsonl", [_tamper_after_the_entry(bet_with_line())])
    )[0]

    def drawn(bet: Bet) -> tuple[Any, ...]:
        chosen = minute_at(bet.minutes, bet.entry_at)
        assert chosen is not None
        return (
            support_segment(chosen, bet.line_span),
            previous_high(bet.minutes, chosen, bet.line_span),
        )

    assert drawn(honest) == drawn(tampered)

    def cheat(bet: Bet) -> tuple[Any, ...]:
        last = bet.minutes[-1]
        return (
            support_segment(last, bet.line_span),
            previous_high(bet.minutes, last, bet.line_span),
        )

    assert cheat(honest) != cheat(tampered), "a trapaça vê o futuro — é isso que o corte impede"


def test_render_writes_one_png_under_the_budget_and_skips_it_next_time(
    bets: list[Bet], tmp_path: Path
) -> None:
    pytest.importorskip("matplotlib", reason="rodar com `uv run --with matplotlib`")
    from meme_render_bets import MAX_PNG_BYTES
    from meme_render_bets_draw import render

    for bet in bets:
        path, written = render(bet, tmp_path)
        assert written is True and path.exists()
        assert path.stat().st_size <= MAX_PNG_BYTES, f"{path.name} passou do teto"
        stamp = path.stat().st_mtime_ns
        again, written_again = render(bet, tmp_path)
        assert written_again is False and again.stat().st_mtime_ns == stamp
        forced, written_forced = render(bet, tmp_path, force=True)
        assert written_forced is True and forced.exists()


def test_the_title_and_the_caption_name_the_set_the_hour_and_what_is_approximate(
    bets: list[Bet],
) -> None:
    pytest.importorskip("matplotlib", reason="rodar com `uv run --with matplotlib`")
    from meme_render_bets_draw import caption, chart_title, levels

    title = chart_title(bets[0])
    assert "flow_v2/2" in title and "WIF" in title
    assert "14/09/2026 02:02 BRT" in title  # 05:02Z − 3 h
    assert "-0.0403 R" in title and "linha rompida" in title
    assert "INDETERMINADO" in chart_title(bets[2])
    text = caption(bets[0], "15s", [], ["alvo ≈ 3× = 361,50"])
    assert "fora da escala (SOL): alvo ≈ 3× = 361,50" in text
    assert "mcap teórico em SOL (T4-MEME-RADAR §4)" in text
    assert "fotografias `curve`/`pool`" in text
    assert "as regras medem a marca em SOL" in text
    # 120,5 × 3 = 361,5 (alvo) e 120,5 × 0,5 = 60,25 (piso de 50 %).
    drawn = {label: value for label, value, _ in levels(bets[0])}
    assert drawn["alvo ≈ 3×"] == Decimal("361.5")
    assert drawn["piso ≈ −50 %"] == Decimal("60.250")
    assert drawn["arma o trailing ≈ 1.5×"] == Decimal("180.75")


def _vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    vault = tmp_path / "obsidian"
    (vault / "05-EXPERIMENTS").mkdir(parents=True)
    (vault / "05-EXPERIMENTS" / "EXP-M5-fluxo-e-holders.md").write_text("x", encoding="utf-8")
    (vault / "05-EXPERIMENTS" / "EXP-M2-a-linha-manda.md").write_text("x", encoding="utf-8")
    (vault / "03-TRADING" / "Meme").mkdir(parents=True)
    (vault / "03-TRADING" / "Meme" / "README.md").write_text("# Meme\n", encoding="utf-8")
    (vault / "09-OPERATIONS" / "Diario-Meme").mkdir(parents=True)
    monkeypatch.setattr(notes_mod, "VAULT", vault)
    monkeypatch.setattr(notes_mod, "SETS_DIR", vault / "03-TRADING" / "Meme" / "Apostas-tracadas")
    monkeypatch.setattr(notes_mod, "DIARY_DIR", vault / "09-OPERATIONS" / "Diario-Meme")
    monkeypatch.setattr(notes_mod, "ATTACH", vault / "attachments" / "meme")
    monkeypatch.setattr(notes_mod, "MEME_README", vault / "03-TRADING" / "Meme" / "README.md")
    return vault


def test_the_notes_are_idempotent_and_never_rewrite_another_day(
    bets: list[Bet], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _vault(tmp_path, monkeypatch)
    page = vault / "03-TRADING" / "Meme" / "Apostas-tracadas" / "flow_v2-2.md"

    notes_mod.write_notes(bets)
    first = page.read_text(encoding="utf-8")
    assert "# flow_v2/2 — apostas traçadas" in first
    assert "[[EXP-M5-fluxo-e-holders]]" in first
    assert "| alvo (×) | `3` |" in first
    assert "## Dia 2026-09-14" in first
    # Uma só medida no conjunto: ela é a melhor e a pior, e os dois rótulos
    # dividem o mesmo embed em vez de repetir a imagem.
    assert "**Melhor · Pior**" in first and "**Mais recente**" in first
    assert "| 02:02:35 | WIF |" in first
    assert "rug_no_snapshot (indeterminada: no_snapshot_in_window)" in first

    notes_mod.write_notes(bets)
    assert page.read_text(encoding="utf-8") == first, "a segunda passagem não muda um byte"

    later = [b for b in load_bets(write_jsonl(tmp_path / "d15.jsonl", [_on_the_15th()]))]
    notes_mod.write_notes(later)
    both = page.read_text(encoding="utf-8")
    assert first.split("## Dia 2026-09-14")[1] in both, "o dia 14 continua palavra por palavra"
    assert both.index("## Dia 2026-09-14") < both.index("## Dia 2026-09-15")
    assert "updated: 2026-09-15" in both


def _on_the_15th() -> dict[str, Any]:
    record = bet_with_line()
    return {
        **record,
        "bet_id": "bet-d",
        "day": "2026-09-15",
        "entry_at": (ENTRY_A + timedelta(days=1)).isoformat(),
        "exit_at": (EXIT_A + timedelta(days=1)).isoformat(),
        "r_multiple": "0.5",
    }


def test_the_diary_gains_section_7_after_the_archivists_section_6(
    bets: list[Bet], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _vault(tmp_path, monkeypatch)
    diary = vault / "09-OPERATIONS" / "Diario-Meme" / "2026-09-14.md"
    diary.write_text(
        "---\ntags: [x]\n---\n\n# Diário Meme — 2026-09-14\n\n## 5. Incidentes\n\nnada\n\n"
        "## 6. O que o Lab aprendeu\n\nlição do arquivista\n",
        encoding="utf-8",
    )
    notes_mod.write_notes(bets)
    text = diary.read_text(encoding="utf-8")
    assert "lição do arquivista" in text, "a seção 6 é do arquivista e não se toca"
    assert text.index("## 6.") < text.index("## 7. Gráficos")
    assert "### `flow_v2/2` — 2 aposta(s)" in text
    assert "gráfico ainda não desenhado" in text, "sem PNG no disco, a nota diz isso"
    notes_mod.write_notes(bets)
    assert diary.read_text(encoding="utf-8") == text, "a seção 7 é substituída por si mesma"


def test_the_index_and_the_inbound_link_keep_the_page_out_of_the_orphan_list(
    bets: list[Bet], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _vault(tmp_path, monkeypatch)
    notes_mod.write_notes(bets)
    index = (vault / "03-TRADING" / "Meme" / "Apostas-tracadas" / "README.md").read_text(
        encoding="utf-8"
    )
    assert "- [[03-TRADING/Meme/Apostas-tracadas/flow_v2-2]]" in index
    assert "- [[03-TRADING/Meme/Apostas-tracadas/trendline_v0-1]]" in index
    readme = (vault / "03-TRADING" / "Meme" / "README.md").read_text(encoding="utf-8")
    assert notes_mod.INDEX_LINK in readme
    notes_mod.write_notes(bets)
    assert (vault / "03-TRADING" / "Meme" / "README.md").read_text(encoding="utf-8") == readme


def test_the_embed_points_at_the_png_that_exists(
    bets: list[Bet], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O link é relativo ao vault e o ``+`` de um R positivo vai codificado."""
    vault = _vault(tmp_path, monkeypatch)
    folder = notes_mod.attachments_dir(bets[1].day, bets[1].rule_set)
    folder.mkdir(parents=True)
    (folder / bets[1].filename()).write_bytes(b"png")
    notes_mod.write_notes(bets)
    page = (vault / "03-TRADING" / "Meme" / "Apostas-tracadas" / "trendline_v0-1.md").read_text(
        encoding="utf-8"
    )
    assert "../../../attachments/meme/2026-09-14/trendline_v0-1/0631-BONK-%2B2.15.png" in page
    assert (vault / "attachments" / "meme" / "2026-09-14" / "trendline_v0-1").exists()
