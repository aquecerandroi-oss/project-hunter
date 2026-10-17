"""End to end on synthetic MT5 exports written by the test (TEST FIXTURES — never real data)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from hunter_indicators.b3.calendar_history import sessions_between
from infra.research.b3.mt5_csv import EXPECTED_HEADER
from infra.research.b3.run_family import FreezeViolation, main

pytestmark = pytest.mark.unit


def _rows(
    day: date,
    start: tuple[int, int],
    end: tuple[int, int],
    price: int,
    vol: int,
    rng: np.random.Generator,
) -> tuple[list[str], int]:
    out: list[str] = []
    t = datetime(day.year, day.month, day.day, *start)  # noqa: DTZ001
    stop = datetime(day.year, day.month, day.day, *end)  # noqa: DTZ001
    while t < stop:
        steps = rng.integers(-vol, vol + 1, size=4) * 5
        path = price + np.cumsum(steps)
        o, c = price, int(path[-1])
        hi, lo = max(o, c, int(path.max())), min(o, c, int(path.min()))
        out.append(
            "\t".join(
                (
                    t.strftime("%Y.%m.%d"),
                    t.strftime("%H:%M:%S"),
                    str(o),
                    str(hi),
                    str(lo),
                    str(c),
                    "10",
                    "20",
                    "0",
                )
            )
        )
        price, t = c, t + timedelta(minutes=1)
    return out, price


def write_exports(tmp: Path) -> tuple[Path, Path]:
    rng = np.random.default_rng(2026)
    win_rows: list[str] = []
    ibov_rows: list[str] = []
    win_price, ibov_price = 130000, 129000
    for day in sessions_between(date(2024, 1, 2), date(2024, 2, 9)):
        vol = int(rng.integers(1, 9))
        rows, win_price = _rows(day, (9, 0), (16, 45), win_price, vol, rng)
        win_rows += rows
        rows, ibov_price = _rows(day, (10, 0), (17, 0), ibov_price, vol, rng)
        ibov_rows += rows
    header = "\t".join(EXPECTED_HEADER)
    win = tmp / "WIN$N_M1.csv"
    ibov = tmp / "IBOV_M1.csv"
    win.write_bytes(("\n".join([header, *win_rows]) + "\n").encode("utf-16"))
    ibov.write_bytes(("\n".join([header, *ibov_rows]) + "\n").encode("utf-16"))
    return win, ibov


def test_three_phases_in_order_and_never_overwritten(tmp_path: Path) -> None:
    win, ibov = write_exports(tmp_path)
    out = tmp_path / "run"
    base = [
        "--win",
        str(win),
        "--ibov",
        str(ibov),
        "--utc-offset-hours",
        "-3",
        "--out",
        str(out),
        "--reps",
        "50",
        "--fixture-only",
    ]
    with pytest.raises(FileNotFoundError):
        main(["--phase", "primary", *base])  # nothing frozen yet
    assert main(["--phase", "freeze", *base]) == 0
    assert {p.name for p in out.iterdir()} == {
        "population.txt",
        "plans.txt",
        "config.txt",
        "manifest.txt",
    }
    config = (out / "config.txt").read_text(encoding="utf-8")
    assert "reps=50 seed=20261019" in config
    assert "infra/research/b3/simulate.py" in config and "prereg_frozen.md" in config
    with pytest.raises(FreezeViolation):
        main(["--phase", "freeze", *base])
    with pytest.raises(FreezeViolation, match="primary report"):
        main(["--phase", "holdout", *base])
    assert main(["--phase", "primary", *base]) == 0
    report = (out / "primary_report.md").read_text(encoding="utf-8")
    assert report.count("LIMITE DE DADO") == 3  # six weeks of fixture: far below 24 months
    assert "## H-039" in report and "## H-040" in report and "## H-041" in report
    with pytest.raises(FreezeViolation, match="already ran"):
        main(["--phase", "primary", *base])
    assert main(["--phase", "holdout", *base]) == 0
    assert "holdout (congelado)" in (out / "holdout_report.md").read_text(encoding="utf-8")
    with pytest.raises(FreezeViolation, match="already ran"):
        main(["--phase", "holdout", *base])


def test_a_changed_export_after_the_freeze_is_refused(tmp_path: Path) -> None:
    win, ibov = write_exports(tmp_path)
    out = tmp_path / "run"
    base = [
        "--win",
        str(win),
        "--ibov",
        str(ibov),
        "--utc-offset-hours",
        "-3",
        "--out",
        str(out),
        "--reps",
        "20",
        "--fixture-only",
    ]
    main(["--phase", "freeze", *base])
    text = win.read_bytes().decode("utf-16").replace("\t10\t20\t0\n", "\t11\t20\t0\n", 1)
    win.write_bytes(text.encode("utf-16"))
    with pytest.raises(FreezeViolation, match="population"):
        main(["--phase", "primary", *base])


def test_a_wrong_declared_offset_stops_before_anything_is_written(tmp_path: Path) -> None:
    win, ibov = write_exports(tmp_path)
    out = tmp_path / "run"
    with pytest.raises(ValueError, match="declared"):
        main(
            [
                "--phase",
                "freeze",
                "--win",
                str(win),
                "--ibov",
                str(ibov),
                "--utc-offset-hours",
                "0",
                "--out",
                str(out),
            ]
        )
    assert not out.exists()


def test_a_different_configuration_after_the_freeze_is_refused(tmp_path: Path) -> None:
    win, ibov = write_exports(tmp_path)
    out = tmp_path / "run"
    base = [
        "--win",
        str(win),
        "--ibov",
        str(ibov),
        "--utc-offset-hours",
        "-3",
        "--out",
        str(out),
        "--fixture-only",
    ]
    main(["--phase", "freeze", *base, "--reps", "20"])
    with pytest.raises(FreezeViolation, match="config"):
        main(["--phase", "primary", *base, "--reps", "50"])


def test_the_holdout_must_reproduce_the_published_primary(tmp_path: Path) -> None:
    win, ibov = write_exports(tmp_path)
    out = tmp_path / "run"
    base = [
        "--win",
        str(win),
        "--ibov",
        str(ibov),
        "--utc-offset-hours",
        "-3",
        "--out",
        str(out),
        "--fixture-only",
    ]
    main(["--phase", "freeze", *base, "--reps", "20"])
    main(["--phase", "primary", *base, "--reps", "20"])
    report = out / "primary_report.md"
    report.write_text(report.read_text(encoding="utf-8") + "edited\n", encoding="utf-8")
    with pytest.raises(FreezeViolation, match="published primary"):
        main(["--phase", "holdout", *base, "--reps", "20"])


def test_fewer_replicates_need_the_fixture_flag_and_are_labelled(tmp_path: Path) -> None:
    win, ibov = write_exports(tmp_path)
    out = tmp_path / "run"
    base = ["--win", str(win), "--ibov", str(ibov), "--utc-offset-hours", "-3", "--out", str(out)]
    with pytest.raises(FreezeViolation, match="10000 replicates"):
        main(["--phase", "freeze", *base, "--reps", "20"])
    main(["--phase", "freeze", *base, "--reps", "20", "--fixture-only"])
    main(["--phase", "primary", *base, "--reps", "20", "--fixture-only"])
    assert "NÃO É A CONSULTA" in (out / "primary_report.md").read_text(encoding="utf-8")
