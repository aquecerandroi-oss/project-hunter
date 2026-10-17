"""MT5 bar export loader — synthetic files written by the tests (fixtures only, never real data)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from infra.research.b3.mt5_csv import (
    EXPECTED_HEADER,
    Mt5FormatError,
    OffsetUndetectable,
    TimezoneMismatch,
    confirm_offset,
    decode_export,
    detect_server_offset,
    load_export,
    parse_export,
    require_tick_grid,
    to_bars,
)

pytestmark = pytest.mark.unit

HEADER = "\t".join(EXPECTED_HEADER)
BRT = timedelta(hours=-3)


def row(
    day: str,
    clock: str,
    o: str = "127450",
    h: str = "127600",
    low: str = "127400",
    c: str = "127550",
) -> str:
    return "\t".join((day, clock, o, h, low, c, "120", "340", "0"))


def text(*rows: str) -> str:
    return "\n".join((HEADER, *rows)) + "\n"


def test_header_is_the_mt5_bar_export() -> None:
    assert EXPECTED_HEADER == (
        "<DATE>",
        "<TIME>",
        "<OPEN>",
        "<HIGH>",
        "<LOW>",
        "<CLOSE>",
        "<TICKVOL>",
        "<VOL>",
        "<SPREAD>",
    )


def test_parse_reads_decimals_and_naive_local_times() -> None:
    bars = parse_export(text(row("2024.03.04", "10:00:00"), row("2024.03.04", "10:01")))
    assert bars[0].local_start == datetime(2024, 3, 4, 10, 0)  # noqa: DTZ001
    assert bars[0].open == Decimal("127450") and bars[0].close == Decimal("127550")
    assert (bars[0].tick_volume, bars[0].volume, bars[0].spread) == (120, 340, 0)
    assert bars[1].local_start == datetime(2024, 3, 4, 10, 1)  # noqa: DTZ001


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("<DATE>,<TIME>,<OPEN>\n", "header"),
        (text("2024.03.04\t10:00:00\t1\t2\t3"), "9 fields"),
        (text(row("04/03/2024", "10:00:00")), "date"),
        (text(row("2024.03.04", "10:00:00", h="127000")), "OHLC"),
        (text(row("2024.03.04", "10:01:00"), row("2024.03.04", "10:00:00")), "increasing"),
        (text(row("2024.03.04", "10:00:00"), row("2024.03.04", "10:00:00")), "increasing"),
        (HEADER + "\n", "no bars"),
    ],
)
def test_malformed_exports_are_refused_with_the_line(body: str, message: str) -> None:
    with pytest.raises(Mt5FormatError, match=message):
        parse_export(body)


def test_decode_follows_the_byte_order_mark() -> None:
    body = text(row("2024.03.04", "10:00:00"))
    assert decode_export(body.encode("utf-16")) == body  # BOM + UTF-16 LE
    assert decode_export(b"\xef\xbb\xbf" + body.encode("utf-8")) == body
    assert decode_export(body.encode("utf-8")) == body


def _index_days(first_clock: str, days: int = 5) -> list[str]:
    return [row(f"2024.03.{4 + d:02d}", first_clock) for d in range(days)] + [
        row(f"2024.03.{4 + d:02d}", "16:59:00") for d in range(days)
    ]


def sorted_rows(rows: list[str]) -> str:
    return text(*sorted(rows, key=lambda r: r.split("\t")[:2]))


def test_detects_brt_and_utc_servers_from_the_first_index_minute() -> None:
    assert detect_server_offset(parse_export(sorted_rows(_index_days("10:00:00")))) == BRT
    assert detect_server_offset(parse_export(sorted_rows(_index_days("13:00:00")))) == timedelta(0)


def test_end_of_bar_stamps_or_pre_opening_are_not_guessed() -> None:
    with pytest.raises(OffsetUndetectable, match="10:01"):
        detect_server_offset(parse_export(sorted_rows(_index_days("10:01:00"))))
    with pytest.raises(OffsetUndetectable, match="09:45"):
        detect_server_offset(parse_export(sorted_rows(_index_days("09:45:00"))))


def test_declared_offset_must_match_or_be_confirmed_by_hand() -> None:
    confirm_offset(BRT, BRT, manual_reason=None)
    with pytest.raises(TimezoneMismatch):
        confirm_offset(timedelta(0), BRT, manual_reason=None)
    with pytest.raises(TimezoneMismatch, match="reason"):
        confirm_offset(BRT, None, manual_reason=None)
    confirm_offset(
        BRT, None, manual_reason="Everton: relógio do Market Watch = Brasília (print 18/10)"
    )
    with pytest.raises(TimezoneMismatch):
        confirm_offset(
            timedelta(0), BRT, manual_reason="override"
        )  # never overrides a contradiction


def test_to_bars_applies_the_declared_offset_and_returns_utc() -> None:
    bars = to_bars(parse_export(text(row("2024.03.04", "10:00:00"))), BRT)
    assert bars[0].start == datetime(2024, 3, 4, 13, 0, tzinfo=UTC)
    assert bars[0].minutes == 1


def test_tick_grid_catches_an_adjusted_series() -> None:
    good = to_bars(parse_export(text(row("2024.03.04", "10:00:00"))), BRT)
    require_tick_grid(good, Decimal(5))
    adjusted = to_bars(
        parse_export(text(row("2024.03.04", "10:00:00", o="127451.37", c="127551"))), BRT
    )
    with pytest.raises(Mt5FormatError, match="tick"):
        require_tick_grid(adjusted, Decimal(5))


def test_load_export_reads_a_file(tmp_path: Path) -> None:
    path = tmp_path / "WIN$N_M1.csv"
    path.write_bytes(text(row("2024.03.04", "10:00:00")).encode("utf-16"))
    bars = load_export(path, BRT)
    assert bars[0].start == datetime(2024, 3, 4, 13, 0, tzinfo=UTC)
