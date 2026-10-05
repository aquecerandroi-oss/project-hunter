"""R87 — carrega o dado real da H-028 num `Market`: painel à vista do R84 (sem ligações de ticker), perpétuos, marca e
funding baixados pelo download87.py. Nada de rede nem base aqui.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
R84 = HERE.parent / "r84"
sys.path.insert(0, str(R84))
sys.path.insert(0, str(HERE))
from config import AS_OF_DAY, EXCLUDED, load_rows, trading_symbols  # noqa: E402
from engine87 import DAY_MS, Market  # noqa: E402
from gaps import KEEP_TOGETHER  # noqa: E402
from panel import build_panel  # noqa: E402

CACHE = HERE / "cache"
PREFIXES = (("", 1.0), ("1000", 1e3), ("1000000", 1e6), ("1M", 1e6))
SPLIT_GAP = 14


_KL: dict[Path, dict[int, tuple[float, float, float, float]]] = {}
_FU: dict[Path, tuple[np.ndarray, np.ndarray]] = {}
_RAW: list = []


def _read_klines(path: Path, as_of_day: int) -> dict[int, tuple[float, float, float, float]]:
    if path not in _KL:
        out: dict[int, tuple[float, float, float, float]] = {}
        with path.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                d = int(r["open_ms"]) // DAY_MS
                out.setdefault(d, (float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])))
        _KL[path] = out
    return {d: v for d, v in _KL[path].items() if d < as_of_day}


def _read_funding(path: Path, max_ms: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    if path not in _FU:
        seen: dict[int, float] = {}
        with path.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                seen.setdefault(int(r["funding_ms"]), float(r["rate"]))
        ms = np.array(sorted(seen), dtype=np.int64)
        _FU[path] = (ms, np.array([seen[m] for m in ms], dtype=float))
    ms, rt = _FU[path]
    if max_ms is None:
        return ms, rt
    k = int(np.searchsorted(ms, max_ms, "right"))
    return ms[:k], rt[:k]


def perp_for(sym: str) -> tuple[str, float] | None:
    base = sym[:-4]
    for pre, mult in PREFIXES:
        name = pre + base + "USDT"
        f = CACHE / "perp_1d" / f"{name}.csv"
        if f.exists() and f.stat().st_size > 40:
            return name, mult
    return None


def load_market(as_of_day: int = AS_OF_DAY, cut_day: int | None = None, cut_funding_ms: int | None = None) -> tuple[Market, dict]:
    """`cut_day`/`cut_funding_ms`: só para o teste de antecipação no dado real (velas < cut_day, funding ≤ cut_ms)."""
    if not _RAW:
        _RAW.extend(load_rows())
    raw = _RAW
    rows = raw if cut_day is None else [r for r in raw if r[1] < cut_day]
    p = build_panel(rows, set(trading_symbols()), EXCLUDED, as_of_day, keep_together=KEEP_TOGETHER,
                    day0=min(r[1] for r in raw), day_end=as_of_day - 1)
    s, n_days = len(p.ids), p.open.shape[1]
    arrs = {k: np.full((s, n_days), np.nan) for k in ("fo", "fh", "fc", "mo", "mh", "ml")}
    mult = np.full(s, np.nan)
    segs: list[list[tuple[int, int, bool]]] = [[] for _ in range(s)]
    fms: list[np.ndarray] = [np.zeros(0, dtype=np.int64)] * s
    frt: list[np.ndarray] = [np.zeros(0)] * s
    status = {x["symbol"]: x["status"] for x in json.loads((CACHE / "fapi_exchange_info.json").read_text(encoding="utf-8"))["symbols"]}
    info = {"mapped": 0, "multiplied": [], "no_perp": 0, "perp_segments_split": []}
    cache: dict[str, tuple] = {}
    lim = as_of_day if cut_day is None else min(cut_day, as_of_day)
    for i, sid in enumerate(p.ids):
        sym = sid.split("#")[0]
        hit = perp_for(sym)
        if hit is None:
            info["no_perp"] += 1
            continue
        name, m = hit
        if name not in cache:
            kl = _read_klines(CACHE / "perp_1d" / f"{name}.csv", lim)
            mk_ = _read_klines(CACHE / "mark_1d" / f"{name}.csv", lim)
            fund = _read_funding(CACHE / "funding" / f"{name}.csv", cut_funding_ms)
            cache[name] = (kl, mk_, fund)
        kl, mk_, (ms, rt) = cache[name]
        if not kl:
            continue
        mult[i] = m
        info["mapped"] += 1
        if m != 1.0:
            info["multiplied"].append(name)
        for d, (o, h, lo, c) in kl.items():
            j = d - p.day0
            if 0 <= j < n_days:
                arrs["fo"][i, j], arrs["fh"][i, j], arrs["fc"][i, j] = o, h, c
        for d, (o, h, lo, c) in mk_.items():
            j = d - p.day0
            if 0 <= j < n_days:
                arrs["mo"][i, j], arrs["mh"][i, j], arrs["ml"][i, j] = o, h, lo
        days = sorted(d - p.day0 for d in kl if 0 <= d - p.day0 < n_days)
        cuts = [0] + [k for k in range(1, len(days)) if days[k] - days[k - 1] - 1 >= SPLIT_GAP] + [len(days)]
        if len(cuts) > 2:
            info["perp_segments_split"].append(name)
        trading_now = status.get(name) == "TRADING"
        for a in range(len(cuts) - 1):
            seg = days[cuts[a]: cuts[a + 1]]
            last_part = a == len(cuts) - 2
            ended = (not last_part) or (not trading_now and seg[-1] < as_of_day - 1 - p.day0)
            segs[i].append((seg[0], seg[-1], ended))
        fms[i], frt[i] = ms, rt
    info["multiplied"] = sorted(set(info["multiplied"]))
    info["perp_segments_split"] = sorted(set(info["perp_segments_split"]))
    mk = Market(p=p, f_open=arrs["fo"], f_high=arrs["fh"], f_close=arrs["fc"], mult=mult, perp_segs=segs,
                fund_ms=fms, fund_rate=frt, m_open=arrs["mo"], m_high=arrs["mh"], m_low=arrs["ml"])
    return mk, info
