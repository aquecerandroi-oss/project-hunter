# R81 — H-021: estrutura do gráfico na hora da compra. Funções puras (IO só em load_*).
# Variáveis do bloco H-021 (Fila de Hipoteses), reconstruídas da fita retrospectiva `meme_trades`
# (block_time; oráculo declarado). Nenhuma decisão da porta tem o bloco `line` nas razões.
from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "infra" / "scripts"))

WINDOW = timedelta(seconds=300)
STEP = timedelta(seconds=60)


def ts(s: str | None) -> datetime | None:
    if s is None or s == "":
        return None
    d = datetime.fromisoformat(s.replace(" ", "T") if "T" not in s else s)
    if d.tzinfo is None:
        raise ValueError(f"timestamp ingénuo: {s}")
    return d.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class Trade:
    block_time: datetime
    received_at: datetime
    slot: int
    order: tuple  # desempate dentro do slot (event_index, outer, inner, signature) — determinístico
    price: Decimal


@dataclass(frozen=True, slots=True)
class Structure:
    price_t: Decimal
    min5: Decimal
    dist: float  # preço na decisão ÷ mínimo dos 5 min − 1 (≥ 0)
    higher_lows: bool | None  # mínimos de [T−180,T−120) < [T−120,T−60) < [T−60,T); janela vazia → None
    breakout: bool | None  # preço na decisão > máxima dos 5 min sem o último slot; sem referência → None
    n_window: int
    last_bt: datetime
    last_recv: datetime  # maior received_at entre as trocas usadas (proveniência)


def structure(trades: list[Trade], decision: datetime, creation_slot: int | None, *,
              received_before_decision: bool = False) -> Structure | None:
    """As três variáveis do bloco H-021 no instante `decision`.

    Só trocas com `block_time < decision` (estrito), fora do slot de criação e com preço > 0; com
    `received_before_decision`, também `received_at < decision` (o que a base tinha). Janela de 5 min
    = [T − 300 s, T). Preço na decisão = o da última troca da janela (ordem block_time, slot, desempate).
    Sem troca na janela → None (ausente, nunca zero)."""
    if decision.tzinfo is None:
        raise ValueError("decisão ingénua")
    lo = decision - WINDOW
    w = [t for t in trades
         if lo <= t.block_time < decision and t.price > 0
         and (creation_slot is None or t.slot != creation_slot)
         and (not received_before_decision or t.received_at < decision)]
    if not w:
        return None
    w.sort(key=lambda t: (t.block_time, t.slot, t.order))
    last = w[-1]
    min5 = min(t.price for t in w)
    dist = float(last.price / min5 - 1)
    mins = []
    for k in (3, 2, 1):
        a, b = decision - k * STEP, decision - (k - 1) * STEP
        ps = [t.price for t in w if a <= t.block_time < b]
        mins.append(min(ps) if ps else None)
    hl = None if any(m is None for m in mins) else (mins[0] < mins[1] < mins[2])
    ref = [t.price for t in w if t.slot < last.slot]
    bo = None if not ref else last.price > max(ref)
    return Structure(last.price, min5, dist, hl, bo, len(w), last.block_time, max(t.received_at for t in w))


def covered(first_bt: datetime | None, decision: datetime) -> bool:
    """"Pelo menos 5 min de trocas antes da decisão": a fita arquivada do mint começa em T − 300 s ou antes."""
    return first_bt is not None and first_bt <= decision - WINDOW


def first_per_mint(rows: list[dict]) -> list[dict]:
    """1.ª decisão por mint: menor decided_at; empate → real; depois entry_at (R80)."""
    best: dict[str, tuple] = {}
    for r in rows:
        k = (ts(r["decided_at"]), 0 if r["lane"] == "real" else 1, ts(r["entry_at"]) or ts(r["decided_at"]), r["bet_id"])
        cur = best.get(r["mint"])
        if cur is None or k < cur[0]:
            best[r["mint"]] = (k, r)
    return [v[1] for v in best.values()]


def resolved(r: dict) -> bool:
    return (r["status"] == "closed" and r["pnl_sol"] != "" and r["size_sol"] != ""
            and Decimal(r["size_sol"]) > 0 and r["oq"] != "indeterminate")


def r_of(r: dict) -> float:
    return float(Decimal(r["pnl_sol"]) / Decimal(r["size_sol"]))


def peak_le_cost(r: dict) -> bool | None:
    """Real: high_water_sol ≤ initial_risk_sol; papel: high_water_x ≤ 1 (R79/R80)."""
    if r["lane"] == "real":
        if not r["hw_sol"] or not r["cost_sol"]:
            return None
        return Decimal(r["hw_sol"]) <= Decimal(r["cost_sol"])
    if not r["hw_x"]:
        return None
    return Decimal(r["hw_x"]) <= 1


def comprou_no_topo(r: dict) -> bool | None:
    """Classe T4.92: perda e pico ≤ custo; sem marca → None."""
    pk = peak_le_cost(r)
    return None if pk is None else (pk and Decimal(r["pnl_sol"]) < 0)


def load_pop(path: Path = HERE / "cache" / "pop.csv") -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_first(path: Path = HERE / "cache" / "first.csv") -> dict[str, tuple[datetime | None, int | None]]:
    with open(path, newline="", encoding="utf-8") as f:
        return {r["mint"]: (ts(r["first_bt"]), int(r["first_slot"]) if r["first_slot"] else None) for r in csv.DictReader(f)}


def load_trades(path: Path = HERE / "cache" / "trades.csv") -> dict[tuple[str, datetime], list[Trade]]:
    out: dict[tuple[str, datetime], list[Trade]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            key = (r["mint"], ts(r["decided_at"]))
            order = (int(r["event_index"] or 0), int(r["outer_ix_index"] or 0), int(r["inner_ix_index"] or 0), r["signature"])
            out.setdefault(key, []).append(Trade(ts(r["block_time"]), ts(r["received_at"]), int(r["slot"]), order, Decimal(r["price"])))
    return out
