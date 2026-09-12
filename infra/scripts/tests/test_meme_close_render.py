"""``meme_close_render.py`` and ``meme_close_outputs.py`` — the diary's section 6,
the ``M-L`` rows, the batch proposal and the dated EXP evaluation, all pure.

No database. Run: ``uv run pytest infra/scripts/tests/test_meme_close_render.py -q``
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from meme_close_fixtures import close_inputs, synthetic_bets  # noqa: E402
from meme_close_outputs import (  # noqa: E402
    append_evaluation,
    diary_index_line,
    exp_evaluation,
    frozen_prediction,
    inbox_rows,
    next_inbox_number,
    render_lote,
)
from meme_close_render import fill_section_six, render_lessons_section  # noqa: E402
from meme_diary_render import WalletTradeLine  # noqa: E402

pytestmark = pytest.mark.unit


def test_section_six_carries_every_lesson_with_n_ci_and_one_sentence_of_change() -> None:
    body = render_lessons_section(close_inputs(synthetic_bets(40)))
    for heading in (
        "### 6.1 Saídas por motivo",
        "### 6.2 Idade na entrada × R",
        "### 6.3 Progresso na entrada × R",
        "### 6.4 Snipers na entrada × R",
        "### 6.5 Top-10 na entrada × R",
        "### 6.6 Dev na entrada × R",
        "### 6.7 Mesmo slot × R",
        "### 6.8 Criador em série × R",
        "### 6.9 Clones de símbolo × R",
        "### 6.10 Cobertura do dia",
        "### 6.11 Operador",
        "### 6.12 Operações reais × veredito do Lab",
        "### 6.13 Leave-top-out",
        "### 6.14 Comparação com o pré-registro",
        "### 6.15 Nota do arquivista",
    ):
        assert heading in body, heading
    assert body.count("**O que muda amanhã:**") == 14
    assert "n = 40" in body and "IC 95 %" in body
    assert "| `meme_paper_v0/1` | dead | 12 |" in body
    assert "progresso 900/1200 (75 %)" in body and "1380 ticks" in body
    assert "`creator_net_seller_unknown`: 700" in body
    assert "propostas pelo laço 5" in body and "mediana 75 s" in body
    assert "Nenhuma operação real observada" in body
    assert "| `meme_paper_v0/1` | 40 |" in body and "-10.3" in body
    assert "Veredito previsto: `descartar`" in body
    assert "00:10 BRT" in body


def test_below_thirty_the_section_says_insufficient_and_the_stub_is_replaced_once() -> None:
    body = render_lessons_section(close_inputs(synthetic_bets(21)))
    assert body.count("nada muda (n insuficiente: 21 < 30)") == 9
    note = (
        "---\nx\n---\n\n# D\n\n## 5. Incidentes\n\n- nada\n\n## 6. O que o Lab aprendeu\n\n"
        "(a preencher pelo arquivista — Sexta-feira)\n"
    )
    filled = fill_section_six(note, body)
    assert filled is not None and filled.endswith(body) and "(a preencher" not in filled
    assert fill_section_six(filled, body) is None, "a written section 6 is never rewritten"
    assert fill_section_six("# sem seção 6\n", body) is None


def test_inbox_rows_exist_only_past_the_ruler_and_are_numbered_after_the_last() -> None:
    passing = close_inputs(synthetic_bets(40))
    rows = inbox_rows(passing, first_number=4)
    assert rows, "the same-slot contrast of the synthetic day passes the ruler"
    assert rows[0].startswith(
        "| 2026-09-12 | **M-L4** (lição medida; fechamento diário T4.15, dia 2026-09-12)"
    )
    assert rows[0].endswith("| nova |")
    assert "[[09-OPERATIONS/Diario-Meme/2026-09-12]]" in rows[0]
    assert all(row.count("|") == 6 and "\n" not in row for row in rows)
    numbers = [row.split("**M-L")[1].split("**")[0] for row in rows]
    assert numbers == [str(4 + i) for i in range(len(rows))]
    assert inbox_rows(close_inputs(synthetic_bets(21)), first_number=1) == []
    assert next_inbox_number("| x | **M-L2** … |\n| y | **M-L7** … |\n") == 8
    assert next_inbox_number("nothing") == 1


def test_the_lote_is_a_proposal_with_retire_or_keep_and_the_arms_that_passed() -> None:
    text = render_lote(close_inputs(synthetic_bets(40)))
    assert text.startswith("# Lote meme — proposta para 2026-09-13")
    assert "Proposta, não ação" in text
    assert "| `meme_paper_v0/1` | EXP-M1 | 40 | 1 |" in text
    assert "manter (n 40/100, dias 1/30)" in text
    assert "## 2. Braços a pré-registrar" in text and "`same_slot`" in text
    assert "previsão `descartar`" in text
    assert "## 3. O que não fazer" in text and "KB-0092" in text
    quiet = render_lote(close_inputs(synthetic_bets(21)))
    assert "Nenhuma lição passou a régua" in quiet


def test_the_exp_evaluation_is_appended_once_before_the_variants_and_quotes_the_prediction() -> (
    None
):
    page = (
        "---\nexp: EXP-M1\n---\n\n## Previsões congeladas (escritas antes de qualquer dado)\n\n"
        "- **P2 — x.** y.\n- **P3 — acerto.** O alvo de 2× precisa de **≥ 33,3 %**.\n"
        "  Previsão: entre **10 % e 25 %**.\n  **Veredito previsto: `descartar`.**\n"
        "- **P4 — z.** w.\n\n## Avaliações (acrescentadas, nunca reescritas)\n\n*Nenhuma.*\n\n"
        "## Variantes tentadas\n\n| a |\n"
    )
    prediction = frozen_prediction(page)
    assert prediction is not None and prediction.startswith("P3 — acerto.")
    assert "Veredito previsto: `descartar`." in prediction and "\n" not in prediction
    assert frozen_prediction("# sem previsão\n") is None
    inputs = close_inputs(synthetic_bets(40))
    block = exp_evaluation(inputs, inputs.all_time[0], prediction)
    assert block.startswith("### Avaliação de 2026-09-12 — fechamento diário (T4.15)")
    assert "n = 40" in block and "dias distintos = 1" in block
    assert "IC 95 % por blocos de dia — (< 2 dias)" in block
    assert "A previsão congelada dizia" in block and "Veredito previsto: `descartar`" in block
    assert "`result` da frontmatter não muda" in block
    appended = append_evaluation(page, block)
    assert appended is not None
    assert (
        appended.index("*Nenhuma.*")
        < appended.index("### Avaliação de 2026-09-12")
        < appended.index("## Variantes tentadas")
    )
    assert append_evaluation(appended, block) is None, "the same day is never appended twice"
    line = diary_index_line(inputs)
    assert line == (
        "- [[09-OPERATIONS/Diario-Meme/2026-09-12|2026-09-12]] — 40 apostas fechadas, R somado -14.8"
    )


def test_real_trades_are_compared_with_the_labs_verdict_in_numbers() -> None:
    buy = WalletTradeLine(
        wallet="6nAh8drzAYfFZuTFFRgwRdV8tNndFiX1E8NGRAGzSk5F",
        mint="MINTREAL",
        side="buy",
        venue="curve",
        block_time=datetime(2026, 9, 12, 16, 14, 9, tzinfo=UTC),
        sol_total=Decimal("0.99"),
        token_amount=Decimal("1000"),
        reason=None,
        lab_verdicts={"meme_paper_v0/1": "creator_net_seller_unknown", "hype_probe_v0/1": "aceito"},
        position_status="closed",
        realized_pnl_sol=Decimal("-0.4"),
        r_multiple=Decimal("-0.4"),
    )
    sell = WalletTradeLine(
        wallet=buy.wallet,
        mint="MINTREAL",
        side="sell",
        venue="curve",
        block_time=datetime(2026, 9, 12, 16, 20, tzinfo=UTC),
        sol_total=Decimal("0.59"),
        token_amount=Decimal("1000"),
        reason=None,
        lab_verdicts={},
        position_status="closed",
        realized_pnl_sol=Decimal("-0.4"),
        r_multiple=Decimal("-0.4"),
    )
    body = render_lessons_section(close_inputs(synthetic_bets(21), reals=[buy, sell]))
    section = body.split("### 6.12")[1].split("### 6.13")[0]
    assert "| `6nAh8drz` | 1 | 1 | -0.4 |" in section
    assert "`hype_probe_v0/1` aceitaria 1 de 1" in section
    assert (
        "`meme_paper_v0/1` aceitaria 0 de 1" in section and "creator_net_seller_unknown" in section
    )
