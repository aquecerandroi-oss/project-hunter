"""``meme_close_day.py``'s writes against a temporary vault — what ``--apply``
touches, in which order, and what it refuses. The database is a stub here;
the real one is in ``test_meme_close_day_integration.py``.

Run: ``uv run pytest infra/scripts/tests/test_meme_close_day.py -q``
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from meme_close_day import (  # noqa: E402
    DIARY_STUB,
    Targets,
    apply_close,
    default_day,
)
from meme_close_fixtures import close_inputs as _inputs  # noqa: E402
from meme_close_fixtures import synthetic_bets as _bets  # noqa: E402
from meme_diary_render import DiaryInputs, render_diary  # noqa: E402

pytestmark = pytest.mark.unit

DAY = date(2026, 9, 12)


def _vault(tmp_path: Path) -> Targets:
    vault = tmp_path / "obsidian"
    (vault / "09-OPERATIONS" / "Diario-Meme").mkdir(parents=True)
    (vault / "00-INBOX").mkdir()
    (vault / "05-EXPERIMENTS").mkdir()
    (vault / "09-OPERATIONS" / "Diario-Meme" / "README.md").write_text(
        "---\ntags: [x]\nstatus: vivo\nowner: sexta-feira\nupdated: 2026-09-12\n---\n# README\n",
        encoding="utf-8",
    )
    (vault / "00-INBOX" / "Hipoteses-do-plantao.md").write_text(
        "---\ntags: [x]\nstatus: viva\nowner: sexta-feira\nupdated: 2026-09-12\n---\n"
        "| data | hipótese | fonte | como testar no Lab | status |\n|---|---|---|---|---|\n"
        "| 2026-09-12 | **M-P33** x | y | z | nova |\n",
        encoding="utf-8",
    )
    (vault / "05-EXPERIMENTS" / "EXP-M1-comprar-cedo-na-curva.md").write_text(
        "---\nexp: EXP-M1\n---\n\n## Previsões congeladas\n\n- **P3 — a.** **Veredito previsto: `descartar`.**\n\n"
        "## Avaliações (acrescentadas, nunca reescritas)\n\n*Nenhuma.*\n\n## Variantes tentadas\n\n| a |\n",
        encoding="utf-8",
    )
    state = tmp_path / "state"
    state.mkdir()
    return Targets(vault_root=vault, state_dir=state)


def _diary(**overrides: Any) -> DiaryInputs:
    base: dict[str, Any] = {
        "day": DAY,
        "generated_at": datetime(2026, 9, 13, 3, 10, tzinfo=UTC),
        "rule_sets": [],
        "bets": [],
        "unfilled_by_refusal": {},
        "expired_proposals": 0,
        "gaps_by_stream_reason": {},
        "sol_usd": None,
        "sol_usd_source": None,
        "sol_usd_observed_at": None,
        "clock_start": None,
        "lab_last_tick_at": None,
    }
    base.update(overrides)
    return DiaryInputs(**base)


def test_the_default_day_is_the_brasilia_day_that_just_closed() -> None:
    assert default_day(datetime(2026, 9, 13, 3, 10, tzinfo=UTC)) == date(2026, 9, 12)  # 00:10 BRT
    assert default_day(datetime(2026, 9, 13, 2, 50, tzinfo=UTC)) == date(2026, 9, 11)  # 23:50 BRT


def test_apply_writes_the_five_outputs_once_and_refuses_a_closed_day(tmp_path: Path) -> None:
    targets = _vault(tmp_path)
    inputs = _inputs(_bets(40))
    note = render_diary(_diary())
    assert note.rstrip().endswith(DIARY_STUB)
    actions = apply_close(
        note, inputs, targets, predictions={"EXP-M1": "P3 — a. **Veredito previsto: `descartar`.**"}
    )
    diary = targets.vault_root / "09-OPERATIONS" / "Diario-Meme" / "2026-09-12.md"
    inbox = (targets.vault_root / "00-INBOX" / "Hipoteses-do-plantao.md").read_text(
        encoding="utf-8"
    )
    exp = (targets.vault_root / "05-EXPERIMENTS" / "EXP-M1-comprar-cedo-na-curva.md").read_text(
        encoding="utf-8"
    )
    readme = (targets.vault_root / "09-OPERATIONS" / "Diario-Meme" / "README.md").read_text(
        encoding="utf-8"
    )
    lote = targets.state_dir / "lote-meme-2026-09-13.md"
    assert diary.exists() and "### 6.7 Mesmo slot × R" in diary.read_text(encoding="utf-8")
    assert "**M-L1**" in inbox and inbox.count("fechamento diário T4.15, dia 2026-09-12") >= 1
    assert "### Avaliação de 2026-09-12 — fechamento diário (T4.15)" in exp
    assert "[[09-OPERATIONS/Diario-Meme/2026-09-12|2026-09-12]]" in readme
    assert lote.exists() and lote.read_text(encoding="utf-8").startswith(
        "# Lote meme — proposta para 2026-09-13"
    )
    assert [a.split(":")[0] for a in actions] == ["diário", "EXP-M1", "INBOX", "README", "lote"]
    # A diary already written by ``meme_diary.py --apply`` (section 6 still the stub) is completed…
    diary.write_text(note, encoding="utf-8")
    again = apply_close(note, inputs, targets, predictions={})
    assert again[0].startswith("diário: seção 6 completada")
    assert all(("mantido" in a or "já existe" in a) for a in again[1:]), again
    assert inbox.count("**M-L1**") == 1
    # …and one whose section 6 was written is refused before anything else is touched.
    with pytest.raises(SystemExit) as refused:
        apply_close(note, inputs, targets, predictions={})
    assert refused.value.code == 2
