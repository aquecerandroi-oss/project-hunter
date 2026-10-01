"""H-026 B coorte prospectiva — testes do detector diário (séries SINTÉTICAS, valores conhecidos).

Rodar:
    uv run --no-sync pytest -q .claude/state/h026b-forward/test_detect_daily.py

Reaproveita a geometria congelada do R85 (`r85/geom85.py`); aqui só se testa o que é novo: o rompimento de topo sem
LTA (`brk.py`), o registro de um dia (`detect_day`), o log só-de-acréscimo e as guardas (dia fechado, base nova sem
classificação, antecipação).
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "r85"))

from brk import plain_breakout  # noqa: E402
from detect_daily import (  # noqa: E402
    UnclassifiedBaseError,
    a20_of,
    detect_day,
    groups_of,
    lookahead_divergences,
)
from guards import (  # noqa: E402
    CohortClosedError,
    FrozenMismatchError,
    LockedError,
    LogOrderError,
    NotClosedError,
    append_record,
    assert_closed,
    check_frozen,
    coverage_gaps,
    load_classified,
    run_lock,
)

# ------------------------------------------------------------------------------ séries sintéticas

OFF = 20
A_IDX = OFF + 10
B_IDX = A_IDX + 20
DAY0 = 20_000  # dia UTC (época) da primeira vela sintética


def _lta_path() -> np.ndarray:
    """O mesmo caminho do teste de LTA do R85: A em b+16, B em b+22 (topo 141 em b+10), linha morre em b+27."""
    c = [160.0 - 2 * i for i in range(OFF)]
    c += [120.0 - 2 * i for i in range(10)]
    c += [101.0]
    c += [101.0 + 3 * i for i in range(1, 10)]
    c += [126.0, 124, 122, 120, 118, 116, 115, 114, 113, 112, 111]
    c += [114.0, 117, 120, 123, 126, 129, 132, 135, 138, 140]
    c += [136.0, 132, 128, 124, 121, 119]
    c += [123.0, 127, 131, 135, 139, 142]
    c += [144.0, 146, 148, 150]
    c += [120.0, 110]
    c += [111.0, 112, 113]
    return np.array(c)


def _random_close(n: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(rng.normal(0.001, 0.04, n)))


def _rows(sym: str, close: np.ndarray, vol: float) -> list[tuple]:
    out = []
    for k, c in enumerate(close):
        o = float(close[k - 1]) if k else float(c)
        out.append((sym, DAY0 + k, o, float(max(o, c) + 1.0), float(min(o, c) - 1.0), float(c), vol))
    return out


def _panel_rows() -> list[tuple]:
    n = _lta_path().size
    return (_rows("AAAUSDT", _lta_path(), 3e6) + _rows("BBBUSDT", _random_close(n, 1), 2e6)
            + _rows("CCCUSDT", _random_close(n, 2), 1e6))


TRADING = {"AAAUSDT", "BBBUSDT", "CCCUSDT"}
KNOWN = {"AAA", "BBB", "CCC"}


def _detect(rows, day, **kw):
    return detect_day(rows, day, TRADING, known_bases=kw.pop("known", KNOWN), classified=kw.pop("classified", {}))


# ------------------------------------------------------------------------------ rompimento de topo sem LTA


def test_plain_breakout_known_bars() -> None:
    c = _lta_path()
    h = np.maximum(c, np.concatenate([[c[0]], c[:-1]])) + 1.0  # as máximas que `_rows` grava
    out = plain_breakout(h, c)
    # pivô de alta em a+9 (máx 129) → 1.º fechamento acima em b+7 (132); pivô em b+10 (máx 141) → b+22 (142)
    assert list(np.flatnonzero(out)) == [B_IDX + 7, B_IDX + 22]


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_plain_breakout_does_not_change_when_future_or_forming_candle_changes(seed: int) -> None:
    c = _random_close(500, seed)
    h = c * 1.02
    full = plain_breakout(h, c)
    for t in range(15, 500, 5):
        assert plain_breakout(h[: t + 1], c[: t + 1])[t] == full[t]
    h2, c2 = h.copy(), c.copy()
    h2[301], c2[301] = h[301] * 5, c[301] * 4  # a vela 301 "em formação" muda à vontade
    assert np.array_equal(plain_breakout(h2, c2)[:301], plain_breakout(h[:301], c[:301]))


# ------------------------------------------------------------------------------ o registro de um dia


def test_detect_day_flags_the_known_b_event_and_keeps_it_out_of_the_comparator() -> None:
    rec = _detect(_panel_rows(), DAY0 + B_IDX + 22)
    assert rec["signal_day"] == "2024-12-15"  # DAY0 + 72
    assert [m["symbol"] for m in rec["universe"]] == ["AAAUSDT", "BBBUSDT", "CCCUSDT"]
    aaa = rec["universe"][0]
    assert aaa["flags"] == {"B": True, "A": False, "brk": True, "ctrl_lta": False, "a20": True}
    assert rec["groups"]["event_B"] == ["AAAUSDT"]
    assert rec["groups"]["event_B_brk"] == ["AAAUSDT"]
    assert "AAAUSDT" not in rec["groups"]["cmp_brk_sem_teste"]  # rompimento que É o B não serve de comparação
    assert aaa["close"] == pytest.approx(142.0)
    assert (aaa["segment_start"], aaa["traded_as"]) == ("2024-10-04", "AAAUSDT")  # identidade estável (Astra #5)


def test_detect_day_on_the_a_touch_and_on_control_days() -> None:
    rows = _panel_rows()
    assert _detect(rows, DAY0 + B_IDX + 16)["universe"][0]["flags"]["A"] is True
    ctrl = _detect(rows, DAY0 + B_IDX + 18)
    assert ctrl["universe"][0]["flags"] == {"B": False, "A": False, "brk": False, "ctrl_lta": True, "a20": True}
    early = _detect(rows, DAY0 + B_IDX + 7)  # rompimento simples sem teste de LTA nas 20 velas: comparador
    assert early["universe"][0]["flags"]["brk"] and not early["universe"][0]["flags"]["a20"]
    assert "AAAUSDT" in early["groups"]["cmp_brk_sem_teste"]
    assert "AAAUSDT" in ctrl["groups"]["ctrl_lta"]


def test_record_ignores_forming_and_future_candles() -> None:
    rows = _panel_rows()
    d = DAY0 + B_IDX + 21  # véspera do B
    base = _detect(rows, d)
    wild = [r for r in rows if r[1] <= d] + [("AAAUSDT", d + 1, 141.0, 900.0, 1.0, 800.0, 9e9),
                                            ("BBBUSDT", d + 3, 1.0, 2.0, 0.5, 1.5, 9e12)]
    assert _detect(wild, d) == base
    assert lookahead_divergences(_detect, rows, list(range(DAY0 + 40, DAY0 + 79))) == []


def test_guard_catches_a_deliberate_lookahead_cheat() -> None:
    """Detector trapaceiro: marca B quando o fechamento de amanhã é maior que o de hoje (lê a vela d + 1)."""

    def cheat(rows, day, **kw):
        rec = _detect(rows, day)
        nxt = {r[0]: r[5] for r in rows if r[1] == day + 1}
        for m in rec["universe"]:
            m["flags"]["B"] = nxt.get(m["symbol"], 0.0) > (m["close"] or np.inf)
        return rec

    assert len(lookahead_divergences(cheat, _panel_rows(), list(range(DAY0 + 40, DAY0 + 79)))) > 0


def test_unclassified_new_base_blocks_the_day_until_classified() -> None:
    rows = _panel_rows() + _rows("NEWUSDT", _random_close(_lta_path().size, 9), 5e6)
    with pytest.raises(UnclassifiedBaseError, match="NEW"):
        _detect(rows, DAY0 + 70)
    rec = _detect(rows, DAY0 + 70, classified={"NEW": True})  # classificada como paridade fiduciária: fora
    assert "NEWUSDT" not in [m["symbol"] for m in rec["universe"]]
    rec = _detect(rows, DAY0 + 70, classified={"NEW": False})
    assert rec["universe"][0]["symbol"] == "NEWUSDT"


def test_groups_common_trigger_comparator_astra_1() -> None:
    def m(sym: str, **f: bool) -> dict:
        return {"symbol": sym, "flags": {"B": False, "A": False, "brk": False, "ctrl_lta": False, "a20": False} | f}

    g = groups_of([m("E", B=True, brk=True, a20=True), m("Bsolo", B=True, a20=True), m("C", brk=True),
                   m("Testada", brk=True, a20=True), m("Toque", A=True, a20=True), m("R", ctrl_lta=True, a20=True)])
    assert g["event_B"] == ["E", "Bsolo"]
    assert g["event_B_brk"] == ["E"]  # P: só os B que também são rompimento simples (gatilho comum)
    assert g["cmp_brk_sem_teste"] == ["C"]  # rompimento sem toque >= 3 nas 20 velas: nem B nem armado para B
    assert g["ctrl_lta"] == ["R"]
    assert g["event_A"] == ["Toque"]


# ------------------------------------------------------------------------------ dia fechado e log só-de-acréscimo


def test_assert_closed_needs_the_next_utc_midnight() -> None:
    d = DAY0 + 10
    midnight = dt.datetime(1970, 1, 1, tzinfo=dt.UTC) + dt.timedelta(days=d + 1)
    with pytest.raises(NotClosedError):
        assert_closed(d, midnight - dt.timedelta(seconds=1))
    assert_closed(d, midnight)
    with pytest.raises(NotClosedError):  # o CLI usa 00:10Z (Astra, nice-to-have)
        assert_closed(d, midnight + dt.timedelta(minutes=9, seconds=59), margin_s=600)
    assert_closed(d, midnight + dt.timedelta(minutes=10), margin_s=600)


def _rec(day: int) -> dict:
    return {"signal_day": (dt.date(1970, 1, 1) + dt.timedelta(days=day)).isoformat(), "as_of": "x", "universe": []}


def test_append_is_idempotent_and_never_rewrites_past_rows(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    d = DAY0 + 50
    assert append_record(log, _rec(d), first_day=d) is True
    before = log.read_bytes()
    assert append_record(log, _rec(d), first_day=d) is False  # mesmo dia de novo: nada muda
    assert log.read_bytes() == before
    assert append_record(log, _rec(d + 1), first_day=d) is True
    after = log.read_bytes()
    assert after.startswith(before)
    assert [json.loads(x)["signal_day"] for x in after.decode().splitlines()] == [_rec(d)["signal_day"],
                                                                                 _rec(d + 1)["signal_day"]]


def test_append_refuses_holes_days_before_the_start_and_the_past(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    d = DAY0 + 50
    with pytest.raises(LogOrderError):
        append_record(log, _rec(d - 1), first_day=d)  # antes do início da coorte
    with pytest.raises(LogOrderError):
        append_record(log, _rec(d + 1), first_day=d)  # o primeiro dia tem de ser o início
    append_record(log, _rec(d), first_day=d)
    with pytest.raises(LogOrderError):
        append_record(log, _rec(d + 2), first_day=d)  # buraco no calendário


def test_truncated_last_line_is_refused_not_skipped(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    d = DAY0 + 50
    append_record(log, _rec(d), first_day=d)
    with log.open("a", encoding="utf-8") as fh:
        fh.write('{"signal_day": "20')  # queda no meio da escrita
    with pytest.raises(LogOrderError, match="inválida"):
        append_record(log, _rec(d + 1), first_day=d)


def test_run_lock_refuses_a_concurrent_run(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    with run_lock(log):
        with pytest.raises(LockedError):
            with run_lock(log):
                pass
    with run_lock(log):  # liberado ao sair
        pass


def test_frozen_manifest_refuses_an_edited_prereg_code_or_base(tmp_path: Path) -> None:
    pre, frozen = tmp_path / "PREREG.md", tmp_path / "frozen.json"
    pre.write_text("bloco", encoding="utf-8")
    shas = {"code_sha256": "c1", "base_sha256": "b1"}
    check_frozen(pre, frozen, shas, freeze=True)
    check_frozen(pre, frozen, shas)
    with pytest.raises(FrozenMismatchError, match="code"):  # alguém mexeu em geom85/exclusões (Astra r2 #3)
        check_frozen(pre, frozen, {"code_sha256": "c2", "base_sha256": "b1"})
    with pytest.raises(FrozenMismatchError, match="base"):
        check_frozen(pre, frozen, {"code_sha256": "c1", "base_sha256": "b2"})
    pre.write_text("bloco editado", encoding="utf-8")
    with pytest.raises(FrozenMismatchError, match="prereg"):
        check_frozen(pre, frozen, shas)
    with pytest.raises(FrozenMismatchError):
        check_frozen(pre, frozen, shas, freeze=True)  # congelar de novo não sobrescreve o manifesto


def test_classification_file_only_grows(tmp_path: Path) -> None:
    f = tmp_path / "classified_bases.jsonl"
    assert load_classified(f, 0, None) == ({}, 0, None)
    f.write_text('{"base": "NEW", "excluded": true, "reason": "paridade USD"}\n', encoding="utf-8")
    cls, n, sha = load_classified(f, 0, None)
    assert cls == {"NEW": True}
    with f.open("a", encoding="utf-8") as fh:
        fh.write('{"base": "XYZ", "excluded": false, "reason": "token comum"}\n')
    assert load_classified(f, n, sha)[0] == {"NEW": True, "XYZ": False}
    n2, sha2 = load_classified(f, n, sha)[1:]
    with f.open("a", encoding="utf-8") as fh:  # acrescentar a mesma base com outro rótulo (Astra r3 #1)
        fh.write('{"base": "NEW", "excluded": false, "reason": "mudou de ideia"}\n')
    with pytest.raises(FrozenMismatchError, match="NEW"):
        load_classified(f, n2, sha2)
    f.write_text('{"base": "NEW", "excluded": false, "reason": "mudou de ideia"}\n', encoding="utf-8")
    with pytest.raises(FrozenMismatchError):  # reescrever uma classificação antiga é recusado
        load_classified(f, n, sha)


def test_a_missing_candle_blocks_the_day_unless_justified_astra_r2_1() -> None:
    rows = [r for r in _panel_rows() if not (r[0] == "BBBUSDT" and r[1] == DAY0 + 60)]
    status = {"AAAUSDT": "TRADING", "BBBUSDT": "TRADING", "CCCUSDT": "TRADING"}
    assert coverage_gaps(rows, DAY0 + 60, status, set()) == (["BBBUSDT"], [])
    gaps, excused = coverage_gaps(rows, DAY0 + 60, status, {"BBBUSDT:2024-12-03"})
    assert (gaps, excused) == ([], [{"symbol": "BBBUSDT", "day": "2024-12-03", "reason": "aceita à mão (--accept-gap)"}])
    # fora de TRADING: ausência justificada E gravada com o status observado (Astra r3 #2)
    gaps, excused = coverage_gaps(rows, DAY0 + 60, status | {"BBBUSDT": "BREAK"}, set())
    assert (gaps, excused) == ([], [{"symbol": "BBBUSDT", "day": "2024-12-03", "reason": "status BREAK na execução"}])
    gaps, excused = coverage_gaps(rows, DAY0 + 60, {k: v for k, v in status.items() if k != "BBBUSDT"}, set())
    assert excused == [{"symbol": "BBBUSDT", "day": "2024-12-03", "reason": "fora do exchangeInfo na execução"}]
    assert coverage_gaps(rows, DAY0 + 61, status, set()) == ([], [])


def test_cohort_end_is_enforced_astra_r2_4(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    d = DAY0 + 50
    append_record(log, _rec(d), first_day=d, last_day=d)
    with pytest.raises(CohortClosedError):
        append_record(log, _rec(d + 1), first_day=d, last_day=d)


def test_a20_window_is_21_real_candles_including_today() -> None:
    a = np.zeros(40, dtype=bool)
    a[40 - 21] = True  # toque em t − 20: ainda pode armar um B em t
    assert a20_of(a)
    a[:] = False
    a[40 - 22] = True  # toque em t − 21: o B daquela linha já venceu
    assert not a20_of(a)
