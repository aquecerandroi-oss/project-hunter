"""R76 / H-014 — carregador: população, compradoras pré-decisão, rede de financiadores, desfechos.

Tudo o que entra na variável vem de trocas com `block_time < decisão` (oráculo retrospetivo de
`meme_trades`, R73) e de financiamentos com `block_time < decisão`. O desfecho usa o simulador do R72
sem alterações (`simulate_current`), mais a censura por buraco de fita até ao pouso (emenda 3 da Astra).
Dinheiro em lamports inteiros / `Decimal`; tempo UTC aware (datetimes ingénuos são recusados pelo R73).
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = HERE.parent
OUR = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
DUMP_SELLERS, DUMP_WINDOW_S = 10, 300
MAX_GAP_S = 60.0
EXCHANGE_MIN_RECIPIENTS = 1000
csv.field_size_limit(10**8)


def _mod(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = m
    spec.loader.exec_module(m)  # type: ignore[union-attr]
    return m


r73 = _mod("r73load", STATE / "r73" / "load.py")
_self = sys.modules.get("load")
r72 = _mod("load", STATE / "r72" / "load.py")  # sim.py faz `from load import ...`: registo temporário
sim = _mod("r72sim", STATE / "r72" / "sim.py")
sys.modules["r72load"] = r72
if _self is not None:
    sys.modules["load"] = _self
else:
    sys.modules.pop("load", None)
ts = r73.ts


# ----------------------------------------------------------------------------- variável


@dataclass(frozen=True)
class Funding:
    funder: str
    block_time: datetime


def pre_decision_buyers(tape, decision: datetime, exclude: frozenset[str] = frozenset({OUR})) -> list[str]:
    """Carteiras distintas que compraram com `block_time < decisão`, na ordem da 1.ª compra."""
    if decision.tzinfo is None:
        raise ValueError("decisão ingénua")
    seen: dict[str, None] = {}
    for t in tape:
        if t.side == "buy" and t.block_time < decision and t.trader not in exclude:
            seen.setdefault(t.trader, None)
    return list(seen)


def ambiguous_buyers(tape, decision: datetime, exclude: frozenset[str] = frozenset({OUR})) -> int:
    """Compradoras cuja 1.ª compra cai no MESMO segundo da decisão (block_time tem resolução de 1 s)."""
    sec = decision.replace(microsecond=0)
    first: dict[str, datetime] = {}
    for t in tape:
        if t.side == "buy" and t.block_time < decision and t.trader not in exclude:
            first.setdefault(t.trader, t.block_time)
    return sum(1 for v in first.values() if v >= sec)


def resolved(buyers: list[str], funding: dict[str, Funding], decision: datetime) -> dict[str, str]:
    """Compradora → financiador, só se o financiamento é estritamente anterior à decisão."""
    return {b: funding[b].funder for b in buyers if b in funding and funding[b].block_time < decision}


def network(buyers: list[str], funding: dict[str, Funding], decision: datetime,
            is_exchange=lambda funder: False) -> dict[str, object]:
    """`rede_financiadora_pct` (congelada) e companheiras.

    pct = maior grupo (financiador ≠ casa de câmbio) ÷ resolvidas; grupo unitário → 0.
    pct_all = o mesmo numerador ÷ todas as compradoras pré-decisão (sugestão da Astra).
    Sem nenhuma resolvida → pct None (desconhecido, nunca zero).
    """
    res = resolved(buyers, funding, decision)
    groups = Counter(f for f in res.values() if not is_exchange(f))
    top, size = (groups.most_common(1)[0] if groups else (None, 0))
    size = size if size >= 2 else 0
    n_res = len(res)
    return {
        "n_buyers": len(buyers), "n_resolved": n_res,
        "coverage": (n_res / len(buyers)) if buyers else None,
        "max_group": size, "top_funder": top if size else None,
        "pct": (size / n_res) if n_res else None,
        "pct_all": (size / len(buyers)) if buyers else None,
    }


def creator_share(buyers: list[str], funding: dict[str, Funding], decision: datetime,
                  creator: str | None) -> float | None:
    """`financiado_pelo_criador_pct`: financiadas pelo criador ou pelo financiador do criador (1 salto)."""
    if not creator:
        return None
    others = [b for b in buyers if b != creator]
    res = resolved(others, funding, decision)
    if not res:
        return None
    cf = funding.get(creator)
    targets = {creator} | ({cf.funder} if cf and cf.block_time < decision else set())
    return sum(1 for f in res.values() if f in targets) / len(res)


# ------------------------------------------------------------------- casa de câmbio


def exchange_status(rec: dict | None, cut: int, labelled: bool) -> str:
    """'exchange' | 'not' | 'unknown' para um financiador no corte `cut` (unix, decisão do mint).

    `rec` é a resposta de `xfers` pedida com um corte ≥ `cut`; conta-se só o que tem blockTime < cut.
    """
    if labelled:
        return "exchange"
    if rec is None or not rec.get("ok"):
        return "unknown"
    n = sum(1 for bt in rec["first_bt"] if bt < cut)
    if n > EXCHANGE_MIN_RECIPIENTS:
        return "exchange"
    # histórico anterior ao corte do pedido esgotado ⇒ a contagem até `cut` (≤ corte do pedido) é exata
    return "not" if rec["exhausted"] else "unknown"


# ------------------------------------------------------------------------- desfecho


def coordinated_dump(tape, entry: datetime, exclude: frozenset[str] = frozenset({OUR})) -> tuple[bool, int]:
    """≥ 10 vendedoras distintas num mesmo slot com block_time em [entrada, entrada + 300 s]."""
    end = entry + timedelta(seconds=DUMP_WINDOW_S)
    per_slot: dict[int, set[str]] = defaultdict(set)
    for t in tape:
        if t.side == "sell" and entry <= t.block_time <= end and t.trader not in exclude:
            per_slot[t.slot].add(t.trader)
    worst = max((len(v) for v in per_slot.values()), default=0)
    return worst >= DUMP_SELLERS, worst


def landing(P, latency_s: float = sim.LATENCY_S, seconds: int = r72.WINDOW_S):
    """Espelho do laço de `simulate_current`: (motivo, instante do pouso). Conferido contra ele em `outcome`."""
    pts = r72.window(P, seconds, tail_s=latency_s + 2)
    last_trigger = P["entry_bt"] + timedelta(seconds=seconds)
    live = [k for k, p in enumerate(pts) if p[0] <= last_trigger]
    if len(live) < 3:
        return None, None
    spent, tokens = P["spent"], P["tokens"]
    high = pts[0][3]
    target = int(Decimal(spent) * sim.TARGET_X)
    for i in live:
        mark = r72.sell_net(pts[i][1], pts[i][2], tokens)
        high = max(high, mark)
        hit = mark >= target
        if hit or mark <= int(Decimal(high) * (1 - sim.TRAILING)):
            return ("target" if hit else "trailing"), pts[i][0] + timedelta(seconds=latency_s)
    return "time_stop", last_trigger + timedelta(seconds=latency_s)


def max_gap_until(P, until: datetime) -> float:
    """Maior intervalo sem observação no caminho entre a entrada e `until` (inclui a cauda até `until`)."""
    ts_ = [p[0] for p in P["path"] if p[0] <= until]
    if not ts_:
        return float("inf")
    gaps = [(b - a).total_seconds() for a, b in zip(ts_, ts_[1:], strict=False)]
    return max(gaps + [(until - ts_[-1]).total_seconds()])


def outcome(P) -> dict[str, object]:
    """PnL por SOL da regra atual (R72, 2,23 %, 1,6 s) + censura por cobertura (emenda 3)."""
    r72.coverage(P)
    if not r72.resolvable(P):
        return {"sim_ret": None, "censor": "not_resolvable"}
    res = sim.simulate_current(P)
    ret = sim.per_sol(res, P)
    reason, land = landing(P)
    if ret is None or land is None:
        return {"sim_ret": None, "censor": "sim_not_ok"}
    if reason != res["reason"]:
        raise AssertionError(f"landing() divergiu de simulate_current: {reason} × {res['reason']}")
    gap = max_gap_until(P, land)
    return {"sim_ret": float(ret), "sim_reason": reason, "gap_to_landing_s": gap,
            "censor": None if gap <= MAX_GAP_S else "gap>60s"}


# ------------------------------------------------------------------------ população


def _j(s: str):
    try:
        return json.loads(s) if s else {}
    except ValueError:
        return {}


def make_P(r: dict[str, str]) -> dict | None:
    """Posição no formato do simulador do R72 (mesmos campos de `load_real`/`load_paper`)."""
    entry, params = _j(r["entry_json"]), _j(r["params"])
    if r["lane"] == "live":
        if not entry.get("virtual_sol_reserves_after"):
            return None
        return dict(pop="real", pid=r["bet_id"], mint=r["mint"], entry_at=ts(r["entry_at"]),
                    spent=int(r["spent_lamports"]), tokens=int(Decimal(str(entry.get("token_amount", 0)))),
                    entry_slot=int(entry.get("slot") or 0),
                    entry_bt=ts(entry["block_time"]) if entry.get("block_time") else ts(r["entry_at"]),
                    vsol0=int(Decimal(str(entry["virtual_sol_reserves_after"]))),
                    vtok0=int(Decimal(str(entry.get("virtual_token_reserves_after", 0)))), params=params)
    snap = entry.get("snapshot") or {}
    if not snap.get("virtual_sol_reserves"):
        return None
    P = dict(pop="paper", pid=r["bet_id"], mint=r["mint"], entry_at=ts(r["entry_at"]),
             spent=int(Decimal(str(entry.get("sol_spent", "0"))) * 10**9),
             tokens=int(Decimal(str(entry.get("tokens", "0"))) * 10**6), entry_slot=0,
             entry_bt=ts(snap["observed_at"]) if snap.get("observed_at") else ts(r["entry_at"]),
             vsol0=int(Decimal(str(snap["virtual_sol_reserves"])) * 10**9),
             vtok0=int(Decimal(str(snap["virtual_token_reserves"])) * 10**6), params=params)
    return P if P["tokens"] > 0 and P["spent"] > 0 else None


def load_rows(path: Path = HERE / "pop.csv") -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def one_per_mint(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Real ganha de papel; entre iguais, a mais antiga (`decided_at`, depois `bet_id`). Regra do R73/R75."""
    best: dict[str, dict[str, str]] = {}
    for r in rows:
        k = (r["lane"] != "live", ts(r["decided_at"]), r["bet_id"])
        cur = best.get(r["mint"])
        if cur is None or k < (cur["lane"] != "live", ts(cur["decided_at"]), cur["bet_id"]):
            best[r["mint"]] = r
    return sorted(best.values(), key=lambda r: ts(r["decided_at"]))


def birth_coverage(tape, r: dict[str, str]) -> tuple[bool, bool]:
    """(começa no nascimento, reconcilia com a foto ±2 %) — critério do R73, retrospetivo."""
    dec = ts(r["decided_at"])
    nasce, _ = r73.tape_starts_at_birth(tape, ts(r["token_created_at"]) if r["token_created_at"] else None)
    qa = ts(r["quote_observed_at"]) if r["quote_observed_at"] else None
    qs = Decimal(r["quote_real_sol"]) if r["quote_real_sol"] else None
    rec = False
    if qa is not None and qs is not None and qa <= dec:
        rec, _ = r73.tape_matches_curve(tape, qa, qs)
    return nasce, rec


def load_funding(pattern: str = "cache_gtfa*.jsonl") -> tuple[dict[str, Funding], Counter]:
    """Última resposta por carteira; linhas partidas (escrita concorrente) são ignoradas e contadas."""
    last: dict[str, dict] = {}
    status: Counter = Counter()
    for p in sorted(HERE.glob(pattern)):
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                o = json.loads(line)
            except ValueError:
                status["linha_partida"] += 1
                continue
            if "w" in o and (o["w"] not in last or o.get("ok")):
                last[o["w"]] = o
    out: dict[str, Funding] = {}
    for o in last.values():
        if o.get("ok") and o.get("funder") and o.get("block_time") is not None:
            out[o["w"]] = Funding(o["funder"], datetime.fromtimestamp(int(o["block_time"]), UTC))
            status["ok"] += 1
        else:
            status[str(o.get("status"))] += 1
    return out, status
