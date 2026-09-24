"""R77 / H-016 — a cadeia de reservas "sem nós" a partir de uma foto-âncora anterior a `t0`.

Replay contábil aproximado (Astra, ronda 1): as trocas alheias da fita são aplicadas às reservas
virtuais com os montantes históricos fixos (o modelo aditivo do R72, `r72/load.py:build_path`); as nossas
trocas são removidas, e cada foto `solana_rpc` que ressincroniza é descontada do efeito acumulado das
nossas trocas desde a âncora. Não é a curva exata que existiria sem nós: com as trocas alheias
reprecificadas o produto constante seria outro.

Dinheiro em lamports / unidades inteiras de token; tempo UTC aware.
"""

from __future__ import annotations

import csv
import gzip
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import NamedTuple

HERE = Path(__file__).resolve().parent
OUR = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
LOOKBACK_S = 180
csv.field_size_limit(10**8)


class Pt(NamedTuple):
    t: datetime
    vsol: int
    vtok: int
    kind: str  # 'anchor' | 'trade' | 'photo'
    slot: int
    last_in_slot: bool  # troca: é a última TROCA do seu slot (fotos não contam); foto/âncora: sempre True


def ts(s: str) -> datetime:
    s = s.strip().replace(" ", "T")
    if s.endswith("+00"):
        s += ":00"
    d = datetime.fromisoformat(s)
    if d.tzinfo is None or d.tzinfo.utcoffset(d) is None:
        raise ValueError(f"timestamp ingénuo: {s!r}")
    return d


def _delta(tr: dict) -> tuple[int, int]:
    """Efeito da troca nas reservas virtuais: compra põe SOL e tira tokens; venda o inverso."""
    return (tr["sol"], -tr["tok"]) if tr["side"] == "buy" else (-tr["sol"], tr["tok"])


def build_chain(t0: datetime, trades: list[dict], photos: list[dict], lookback_s: int = LOOKBACK_S):
    """Devolve `(pontos, info)`; `pontos` é None quando não há âncora `<= t0` na janela."""
    if t0.tzinfo is None:
        raise ValueError("t0 ingénuo")
    info: dict = {"censor": None, "our_trades": 0, "our_before_anchor": 0, "resync_max_sol": 0.0,
                  "n_photo_resync": 0}
    cand = [p for p in photos if p["slot"] and t0 - timedelta(seconds=lookback_s) <= p["t"] <= t0]
    if not cand:
        info["censor"] = "sem_ancora"
        return None, info
    anchor = max(cand, key=lambda p: (p["t"], p["slot"]))
    a_slot = anchor["slot"]
    info["anchor_slot"] = a_slot
    info["anchor_age_s"] = (t0 - anchor["t"]).total_seconds()
    ours = sorted((tr for tr in trades if tr["trader"] == OUR), key=lambda r: (r["slot"], r["sig"], r["ei"]))
    info["our_before_anchor"] = sum(1 for tr in ours if tr["slot"] <= a_slot)
    ours = [tr for tr in ours if tr["slot"] > a_slot]
    info["our_trades"] = len(ours)
    others = sorted((tr for tr in trades if tr["trader"] != OUR and tr["slot"] > a_slot),
                    key=lambda r: (r["slot"], r["sig"], r["ei"]))
    events = [(tr["slot"], 0, tr["bt"], tr) for tr in others]
    events += [(p["slot"], 1, p["t"], p) for p in photos if p["slot"] and p["slot"] > a_slot]
    events.sort(key=lambda e: (e[0], e[1]))  # estável: trocas mantêm a ordem (slot, signature, ei)

    vsol, vtok = anchor["vsol"], anchor["vtok"]
    pts = [Pt(anchor["t"], vsol, vtok, "anchor", a_slot, True)]
    k_our = 0
    c_sol = c_tok = 0  # efeito acumulado das nossas trocas desde a âncora
    for slot, kind, t, e in events:
        if kind == 0:
            ds, dt = _delta(e)
            vsol, vtok = vsol + ds, vtok + dt
        else:
            while k_our < len(ours) and ours[k_our]["slot"] <= slot:
                ds, dt = _delta(ours[k_our])
                c_sol, c_tok = c_sol + ds, c_tok + dt
                k_our += 1
            nsol, ntok = e["vsol"] - c_sol, e["vtok"] - c_tok
            info["resync_max_sol"] = max(info["resync_max_sol"], abs(nsol - vsol) / 1e9)
            info["n_photo_resync"] += 1
            vsol, vtok = nsol, ntok
        if vsol <= 0 or vtok <= 0:
            info["censor"] = "reservas_invalidas"
            break
        stamp = max(t, pts[-1].t)
        pts.append(Pt(stamp, vsol, vtok, "trade" if kind == 0 else "photo", slot, True))
    # Astra (ronda 2): uma foto que fecha o slot não pode esconder a última troca desse slot.
    # Pontos do mesmo slot são contíguos e as trocas vêm antes da foto (ordenação acima).
    fixed = [p._replace(last_in_slot=p.kind != "trade" or not (
        k + 1 < len(pts) and pts[k + 1].slot == p.slot and pts[k + 1].kind == "trade"))
        for k, p in enumerate(pts)]
    return fixed, info


def state_at(pts: list[Pt], t: datetime) -> int:
    """Índice do último ponto com carimbo `<= t` (o estado conhecido nesse instante)."""
    j = -1
    for k, p in enumerate(pts):
        if p.t <= t:
            j = k
        else:
            break
    if j < 0:
        raise ValueError("nenhum estado conhecido até t")
    return j


def max_gap(pts: list[Pt], t0: datetime, horizon_s: float) -> float:
    """Maior intervalo sem ponto em `[t0, t0 + horizonte]`, contado a partir de `t0` e com a cauda."""
    end = t0 + timedelta(seconds=horizon_s)
    marks = [t0] + [p.t for p in pts if t0 < p.t <= end] + [end]
    return max((b - a).total_seconds() for a, b in zip(marks, marks[1:], strict=False))


def trades_in(trades: list[dict], t0: datetime, seconds: float) -> int:
    end = t0 + timedelta(seconds=seconds)
    return sum(1 for tr in trades if tr["trader"] != OUR and t0 < tr["bt"] <= end)


# ----------------------------------------------------------------------------- leitura


def _open(p: Path):
    return gzip.open(p, "rt", encoding="utf-8", newline="") if p.suffix == ".gz" else p.open(
        encoding="utf-8", newline="")


def load_tape(path: Path = HERE / "cache" / "tape.csv.gz") -> dict[tuple[str, str], list[dict]]:
    out: dict[tuple[str, str], list[dict]] = {}
    with _open(path) as f:
        for r in csv.DictReader(f):
            out.setdefault((r["pop"], r["mint"]), []).append(dict(
                bt=ts(r["block_time"]), slot=int(r["slot"]), sig=r["signature"], ei=int(r["event_index"]),
                trader=r["trader"], side=r["side"], sol=int(r["sol_lamports"]), tok=int(r["token_raw"])))
    return out


def load_photos(path: Path = HERE / "cache" / "snap.csv.gz") -> dict[tuple[str, str], list[dict]]:
    out: dict[tuple[str, str], list[dict]] = {}
    with _open(path) as f:
        for r in csv.DictReader(f):
            out.setdefault((r["pop"], r["mint"]), []).append(dict(
                t=ts(r["observed_at"]), slot=int(r["slot"] or 0),
                vsol=int(Decimal(r["virtual_sol_reserves"]) * 10**9),
                vtok=int(Decimal(r["virtual_token_reserves"]) * 10**6)))
    for v in out.values():
        v.sort(key=lambda p: (p["t"], p["slot"]))
    return out
