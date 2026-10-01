"""H-026 B coorte prospectiva — velas diárias públicas da Binance e arquivo por PRIMEIRA observação.

Cada (símbolo, dia) entra uma vez em `klines_fwd.csv`, com o carimbo de quando foi obtida, e nunca é reescrita. Se a
exchange depois devolver outro valor para o mesmo dia, a diferença vai para `revisions.csv` e a detecção continua
usando o valor visto primeiro (o que se sabia no fechamento). Um símbolo que a API deixar de servir mantém as velas já
arquivadas — a deslistagem não apaga o passado (Astra, revisão do pré-registro, must-fix 4).
Pesquisa: em produção isto é uma tabela Postgres só-de-acréscimo (ver o relatório da tarefa).
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from data85 import Row

API = "https://api.binance.com"
DAY_MS = 86_400_000
FIELDS = ["symbol", "day", "open", "high", "low", "close", "quote_volume"]


def _get(url: str) -> bytes:
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "hunter-research-h026b-forward"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in (418, 429, 500, 502, 503, 504) or attempt == 5:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            if attempt == 5:
                raise
        time.sleep(2 * (attempt + 1))
    raise AssertionError("inalcançável")


def exchange_usdt() -> dict[str, str]:
    """Símbolo → status (TRADING, BREAK, ...) de todos os pares USDT do exchangeInfo de agora."""
    sy = json.loads(_get(f"{API}/api/v3/exchangeInfo"))["symbols"]
    return {s["symbol"]: s["status"] for s in sy if s["quoteAsset"] == "USDT"}


def fetch_klines(sym: str, start_day: int, end_day: int) -> list[Row] | None:
    """Velas 1d com abertura em [start_day, end_day]. None só para o código -1121 (símbolo desconhecido pela API)."""
    out: list[Row] = []
    start, end = start_day * DAY_MS, (end_day + 1) * DAY_MS - 1
    while start <= end:
        try:
            got = json.loads(_get(f"{API}/api/v3/klines?symbol={urllib.parse.quote(sym)}&interval=1d&startTime={start}&endTime={end}&limit=1000"))
        except urllib.error.HTTPError as exc:
            if exc.code == 400:
                if json.loads(exc.read() or b"{}").get("code") == -1121:
                    return None
            raise
        out += [(sym, int(k[0]) // DAY_MS, float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[7])) for k in got]
        if len(got) < 1000:
            break
        start = int(got[-1][0]) + DAY_MS
    return out


def fetch_all(symbols: list[str], start_day: int, end_day: int) -> tuple[list[Row], list[str]]:
    with ThreadPoolExecutor(max_workers=4) as pool:
        res = list(pool.map(lambda s: fetch_klines(s, start_day, end_day), symbols))
    return [r for got in res if got for r in got], [s for s, got in zip(symbols, res, strict=True) if got is None]


def merge(seen: dict[tuple[str, int], Row], fetched: list[Row]) -> tuple[list[Row], list[tuple[Row, Row]]]:
    """(novas, revisões): nova = (símbolo, dia) nunca visto; revisão = valor diferente do visto primeiro."""
    new, rev = [], []
    for r in fetched:
        old = seen.get((r[0], r[1]))
        if old is None:
            new.append(r)
            seen[(r[0], r[1])] = r
        elif old != r:
            rev.append((old, r))
    return new, rev


class ArchiveCorruptError(RuntimeError):
    """Linha do arquivo incompleta ou inválida (queda no meio da escrita?) — reparar à mão, nunca ler como dado."""


def read_archive(path: Path) -> list[Row]:
    """Valida cada linha (8 campos, preços > 0 e finitos, volume ≥ 0, carimbo ISO, fim de linha) antes de aceitar."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if text and not text.endswith("\n"):
        raise ArchiveCorruptError(f"{path.name}: última linha sem fim de linha")
    out: list[Row] = []
    for n, rec in enumerate(csv.reader(text.splitlines()[1:]), start=2):
        try:
            if len(rec) != len(FIELDS) + 1:
                raise ValueError(f"{len(rec)} campos")
            o, h, lo, c, v = (float(x) for x in rec[2:7])
            dt.datetime.fromisoformat(rec[7])
            if not all(math.isfinite(x) and x > 0 for x in (o, h, lo, c)) or not (math.isfinite(v) and v >= 0):
                raise ValueError("valor fora do domínio")
            out.append((rec[0], int(rec[1]), o, h, lo, c, v))
        except ValueError as exc:
            raise ArchiveCorruptError(f"{path.name} linha {n}: {exc}") from exc
    return out


def append_archive(path: Path, revisions: Path, fetched: list[Row], fetched_at: str) -> tuple[int, int]:
    seen = {(r[0], r[1]): r for r in read_archive(path)}
    new, rev = merge(seen, fetched)
    for target, header, lines in (
        (path, [*FIELDS, "fetched_at"], [[*r, fetched_at] for r in new]),
        (revisions, ["symbol", "day", *(f"first_{k}" for k in FIELDS[2:]), *(f"new_{k}" for k in FIELDS[2:]), "fetched_at"],
         [[o[0], o[1], *o[2:], *n[2:], fetched_at] for o, n in rev]),
    ):
        if not lines:
            continue
        fresh = not target.exists()
        with target.open("a", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            if fresh:
                w.writerow(header)
            w.writerows(lines)
    return len(new), len(rev)
