"""H-026 B coorte prospectiva — arquivo de velas por primeira observação (SINTÉTICO; nenhuma rede).

    uv run --no-sync pytest -q .claude/state/h026b-forward/test_archive.py
"""

from __future__ import annotations

import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "r85"))

import archive  # noqa: E402
from archive import (  # noqa: E402
    ArchiveCorruptError,
    append_archive,
    fetch_klines,
    merge,
    read_archive,
)

R1 = ("AAAUSDT", 20724, 1.0, 2.0, 0.5, 1.5, 100.0)
R2 = ("AAAUSDT", 20725, 1.5, 2.5, 1.0, 2.0, 120.0)


def test_merge_keeps_the_first_seen_candle_and_logs_revisions() -> None:
    new, rev = merge({}, [R1, R2])
    assert new == [R1, R2] and rev == []
    seen = {(r[0], r[1]): r for r in [R1, R2]}
    changed = ("AAAUSDT", 20724, 1.0, 2.2, 0.5, 1.5, 100.0)  # a exchange corrigiu a máxima de um dia antigo
    new, rev = merge(seen, [changed, R2])
    assert new == [] and rev == [(R1, changed)]  # o dia continua com o valor visto primeiro; a revisão fica registrada


def test_archive_is_append_only_and_survives_a_symbol_the_api_dropped(tmp_path: Path) -> None:
    path, revs = tmp_path / "klines.csv", tmp_path / "revisions.csv"
    append_archive(path, revs, [R1], "2026-09-29T00:10:00+00:00")
    before = path.read_bytes()
    append_archive(path, revs, [R1, R2], "2026-09-30T00:10:00+00:00")
    assert path.read_bytes().startswith(before)
    # no dia seguinte a API não serve mais o símbolo: nada novo chega, mas as velas já vistas continuam
    append_archive(path, revs, [], "2026-10-01T00:10:00+00:00")
    assert read_archive(path) == [R1, R2]
    append_archive(path, revs, [("AAAUSDT", 20724, 1.0, 9.0, 0.5, 1.5, 100.0)], "2026-10-02T00:10:00+00:00")
    assert read_archive(path) == [R1, R2]
    assert len(revs.read_text(encoding="utf-8").splitlines()) == 2  # cabeçalho + 1 revisão


def _http_400(body: dict) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("u", 400, "Bad Request", None, io.BytesIO(json.dumps(body).encode()))  # type: ignore[arg-type]


def test_only_code_1121_means_unknown_symbol(monkeypatch: pytest.MonkeyPatch) -> None:
    def gone(url: str) -> bytes:
        raise _http_400({"code": -1121, "msg": "Invalid symbol."})

    monkeypatch.setattr(archive, "_get", gone)
    assert fetch_klines("OLDUSDT", 20724, 20726) is None

    def bad_param(url: str) -> bytes:
        raise _http_400({"code": -1100, "msg": "Illegal characters found in parameter"})

    monkeypatch.setattr(archive, "_get", bad_param)
    with pytest.raises(urllib.error.HTTPError):  # erro de parâmetro não vira "deslistado" (Astra #4)
        fetch_klines("AAAUSDT", 20724, 20726)


def test_a_truncated_archive_line_is_refused_not_read_as_data_astra_r2_2(tmp_path: Path) -> None:
    path, revs = tmp_path / "klines.csv", tmp_path / "revisions.csv"
    append_archive(path, revs, [R1], "2026-09-29T00:10:00+00:00")
    with path.open("a", encoding="utf-8") as fh:
        fh.write("AAAUSDT,20725,1.5,2.5,1.0,2.0,10")  # queda no meio: volume cortado, sem fetched_at nem fim de linha
    with pytest.raises(ArchiveCorruptError):
        read_archive(path)
    with pytest.raises(ArchiveCorruptError):
        append_archive(path, revs, [R2], "2026-09-30T00:10:00+00:00")


def test_non_ascii_symbol_is_url_encoded(monkeypatch: pytest.MonkeyPatch) -> None:
    """A Binance lista pares USDT com nome em caracteres CJK; a URL tem de sair codificada (1.ª corrida real, 01/10)."""
    urls: list[str] = []

    def capture(url: str) -> bytes:
        urls.append(url)
        return b"[]"

    monkeypatch.setattr(archive, "_get", capture)
    assert fetch_klines("币安人生USDT", 20724, 20726) == []
    assert urls and urls[0].isascii() and "symbol=%E5%B8%81" in urls[0]
