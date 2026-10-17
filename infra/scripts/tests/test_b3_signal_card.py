"""``b3_signal_card`` (H-038 day card) — parsing and formatting, no IO beyond stdout.

Run: ``uv run pytest infra/scripts/tests/test_b3_signal_card.py -q``
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]


def _load() -> ModuleType:
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(
        "hunter_infra_b3_signal_card_ut", SCRIPTS_DIR / "b3_signal_card.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


card = _load()

# F = 200 000, I = 202 000 → r1 = ln(1.01); WIN 207 150 is within the typo guard of I.
BUY = {
    "--data": "2026-10-19",
    "--fechamento-anterior": "200.000,00",
    "--fechamento-lido-as": "09:15",
    "--ibov-1030": "202.000,00",
    "--lido-as": "10:42",
    "--win": "207150",
    "--agora": "2026-10-19T10:45",
}


def _args(**override: str) -> list[str]:
    merged = BUY | {f"--{k.replace('_', '-')}": v for k, v in override.items()}
    return [part for pair in merged.items() for part in pair]


def _run(args: list[str], out: io.TextIOBase | None = None) -> tuple[int, str]:
    buffer = io.StringIO()
    code = card.main(args, out=buffer)
    return code, buffer.getvalue()


def _record(text: str) -> dict[str, str]:
    line = next(ln for ln in text.splitlines() if ln.startswith("H038|"))
    body, _, digest = line.rpartition("|sha256=")
    assert hashlib.sha256(body.encode("utf-8")).hexdigest()[:16] == digest
    return dict(part.split("=", 1) for part in body.split("|")[1:])


# ---------------------------------------------------------------- parsing


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("130456,78", "130456.78"),
        ("130.456,78", "130456.78"),
        ("130456.78", "130456.78"),
        ("130456", "130456"),
        (" 207150 ", "207150"),
        ("1.234.567,5", "1234567.5"),
    ],
)
def test_parse_number_accepts_brazilian_and_plain_forms(text: str, expected: str) -> None:
    assert card.parse_number(text) == Decimal(expected)


@pytest.mark.parametrize("text", ["130.456", "207.150", "1.234.567"])
def test_parse_number_refuses_the_ambiguous_dot_thousands_form(text: str) -> None:
    with pytest.raises(ValueError, match="ambíguo"):
        card.parse_number(text)


@pytest.mark.parametrize(
    "text",
    ["", "abc", "0", "-5", "1,2,3", "NaN", "inf", "131,300.00", "+131.300", "1e5", "131 300"],
)
def test_parse_number_refuses_everything_else(text: str) -> None:
    with pytest.raises(ValueError):
        card.parse_number(text)


@pytest.mark.parametrize("text", ["10:42", "10h42", "10:42:30", "2026-10-19T10:42"])
def test_parse_instant_reads_brt_and_converts_to_utc(text: str) -> None:
    got = card.parse_instant(text, date(2026, 10, 19))
    assert got.astimezone(UTC).replace(second=0) == datetime(2026, 10, 19, 13, 42, tzinfo=UTC)


def test_parse_instant_keeps_an_explicit_offset_instead_of_overwriting_it() -> None:
    got = card.parse_instant("2026-10-19T13:00Z", date(2026, 10, 19))
    assert got == datetime(2026, 10, 19, 13, 0, tzinfo=UTC)  # 10:00 BRT, not 13:00 BRT


@pytest.mark.parametrize("text", ["25:00", "10:60", "1042", "", "ontem"])
def test_parse_instant_refuses_invalid(text: str) -> None:
    with pytest.raises(ValueError):
        card.parse_instant(text, date(2026, 10, 19))


def test_brazilian_formatting_of_points_money_and_percent() -> None:
    assert card.fmt_points(Decimal("206110")) == "206.110"
    assert card.fmt_index(Decimal("131300")) == "131.300,00"
    assert card.fmt_brl(Decimal("208")) == "R$ 208,00"
    assert card.fmt_pct(Decimal("0.0099503308")) == "+0,9950 %"
    assert card.fmt_pct(Decimal("-0.0100503358")) == "−1,0050 %"


# ---------------------------------------------------------------- the card


def test_buy_card_has_direction_window_stop_exit_and_reason_in_brt() -> None:
    code, text = _run(_args())
    assert code == 0
    assert "SINAL: COMPRA" in text
    assert "WINZ26" in text
    assert "16:30" in text and "16:35" in text
    assert "206.110" in text  # 207150 × 0,995 = 206114,25 → para baixo ao tick
    assert "1.040 pts" in text and "R$ 208,00" in text
    assert "17:00" in text
    assert "+0,9950 %" in text
    assert "não é perda máxima" in text
    assert "sem reentrada" in text.lower()
    assert "impedimento" in text.lower()
    assert "Vale a primeira linha" in text
    assert "Vantagem no WIN não demonstrada" in text
    assert "compre 1" not in text.lower()


def test_sell_card_puts_the_stop_above_rounded_up() -> None:
    code, text = _run(_args(ibov_1030="198.000,00"))
    assert code == 0
    assert "SINAL: VENDA" in text
    assert "−1,0050 %" in text
    assert "208.190" in text  # 207150 × 1,005 = 208185,75 → para cima ao tick


def test_after_3_november_the_window_and_exit_move_to_the_new_grid() -> None:
    code, text = _run(_args(data="2026-11-03", agora="2026-11-03T10:45"))
    assert code == 0
    assert "17:30" in text and "17:35" in text and "18:00" in text


def test_late_reading_is_no_trade_with_the_deadline_in_brt() -> None:
    code, text = _run(_args(lido_as="11:31", agora="2026-10-19T11:35"))
    assert code == 0
    assert "SEM OPERAÇÃO" in text and "11:30" in text


def test_previous_close_received_after_the_deadline_is_no_trade() -> None:
    """Astra must-fix 1: F's own receipt time decides, not the time I was read."""
    code, text = _run(_args(fechamento_lido_as="11:40", agora="2026-10-19T11:45"))
    assert code == 0
    assert "SEM OPERAÇÃO" in text
    assert _record(text)["motivo"] == "received_after_deadline"


def test_previous_close_read_the_evening_before_is_accepted() -> None:
    code, text = _run(_args(fechamento_lido_as="2026-10-16T18:30"))
    assert code == 0
    assert "SINAL: COMPRA" in text
    assert _record(text)["F_recebido"] == "2026-10-16T21:30:00Z"


def test_reading_typed_before_it_exists_is_refused() -> None:
    code, text = _run(_args(lido_as="10:20"))
    assert code == 0
    assert "SEM OPERAÇÃO" in text


def test_agora_with_an_offset_is_respected() -> None:
    """Astra must-fix 3: 13:00Z is 10:00 BRT — before the 10:42 reading, so no signal."""
    code, text = _run(_args(agora="2026-10-19T13:00Z"))
    assert code == 0
    assert "SEM OPERAÇÃO" in text
    assert _record(text)["decisao"] == "2026-10-19T13:00:00Z"


def test_known_impediment_makes_the_session_no_trade_and_is_recorded() -> None:
    code, text = _run([*_args(), "--impedimento", "leilão | no Ibovespa às 10:30"])
    assert code == 0
    assert "SEM OPERAÇÃO" in text
    fields = _record(text)
    assert fields["motivo"] == "known_impediment"
    assert fields["impedimento"] == "leilão / no Ibovespa às 10:30"


def test_holiday_has_no_session() -> None:
    code, text = _run(_args(data="2026-11-02", agora="2026-11-02T10:45"))
    assert code == 0
    assert "SEM OPERAÇÃO" in text and "Finados" in text


def test_win_expiry_day_is_no_trade() -> None:
    code, text = _run(_args(data="2026-12-16", agora="2026-12-16T10:45"))
    assert code == 0
    assert "SEM OPERAÇÃO" in text and "vencimento" in text


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"win": "207152"}, "múltiplo de 5"),
        ({"ibov_1030": "202.000"}, "ambíguo"),
        ({"ibov_1030": "202,000"}, "confira"),  # 202,0 against 200 000: a typo, not a crash
        ({"win": "20715"}, "confira"),  # a missing digit in the WIN price
        ({"ibov_1030": "131,300.00"}, "formato"),
    ],
)
def test_input_errors_are_refused_before_any_card(override: dict[str, str], message: str) -> None:
    code, text = _run(_args(**override))
    assert code == 2
    assert message in text
    assert "SINAL" not in text


def test_date_outside_the_calendar_data_is_an_input_error() -> None:
    code, text = _run(_args(data="2027-01-04", agora="2027-01-04T10:45"))
    assert code == 2 and "calendário" in text


def test_card_ends_with_one_record_line_whose_checksum_verifies() -> None:
    _, text = _run(_args())
    fields = _record(text)
    assert fields["sinal"] == "COMPRA"
    assert fields["data"] == "2026-10-19"
    assert fields["F"] == "200000.00" and fields["I"] == "202000.00"
    assert fields["F_recebido"] == "2026-10-19T12:15:00Z"
    assert fields["I_evento"] == "2026-10-19T13:30:00Z"
    assert fields["recebido"] == "2026-10-19T13:42:00Z"
    assert fields["decisao"] == "2026-10-19T13:45:00Z"
    assert fields["win_ref"] == "207150" and fields["stop"] == "206110"
    assert fields["v"] == "intraday_momentum_win/1"


def test_no_trade_card_also_has_a_record_line() -> None:
    _, text = _run(_args(ibov_1030="200.000,00"))
    fields = _record(text)
    assert fields["sinal"] == "SEM_OPERACAO" and fields["motivo"] == "zero_return"


def test_card_survives_a_cp1252_pipe_on_windows() -> None:
    """A sell card carries U+2212; a cp1252 stdout must be switched to UTF-8, not crash."""
    raw = io.BytesIO()
    out = io.TextIOWrapper(raw, encoding="cp1252")
    assert card.main(_args(ibov_1030="198.000,00"), out=out) == 0
    out.flush()
    text = raw.getvalue().decode("utf-8")
    assert "SINAL: VENDA" in text and "−1,0050 %" in text
