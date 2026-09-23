"""R72 — carrega a populacao de H-009 e reconstroi o caminho da marca, trade a trade.

Metodo herdado de R62/R64/R65 (`.claude/state/r62/analyze.py`, `.claude/state/r64/load.py`):
a partir das reservas exatas do fill de compra, cada trade da fita soma/subtrai nas reservas
virtuais; cada foto `solana_rpc` com slot >= ultimo trade aplicado ressincroniza (cura buracos
da fita). Marca = produto liquido de vender TODO o nosso lote nas reservas do instante, menos
a taxa de curva de 1,25 % (pump.fun 0,95 % + criador 0,30 %).

Duas populacoes:
  - `real`  : `meme_live_positions` status='closed' (89), ancoradas no slot do fill.
  - `paper` : `meme_paper_bets` fechadas, uma por mint, ancoradas no `entry.snapshot`
              (sem slot: a ancora e o `observed_at`; declarado como limitacao).

Dinheiro em lamports inteiros e Decimal. Nada de float em dinheiro.
"""

from __future__ import annotations

import csv
import gzip
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

csv.field_size_limit(20_000_000)

HERE = Path(__file__).resolve().parent
OUR = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
FEE = Decimal("0.0125")  # taxa de curva por perna, ja embutida na marca
BRT = timezone(timedelta(hours=-3))
WINDOW_S = 300


def ts(s: str | None):
    s = (s or "").strip()
    if not s:
        return None
    if s.endswith("+00"):
        s += ":00"
    return datetime.fromisoformat(s.replace(" ", "T"))


def _jload(s):
    try:
        return json.loads(s) if s else None
    except Exception:
        return None


def sell_net(vsol: int, vtok: int, amount: int) -> int:
    """Lamports liquidos de vender `amount` tokens nas reservas (vsol, vtok) — menos 1,25 %."""
    if amount <= 0 or vtok <= 0:
        return 0
    gross = vsol - (vsol * vtok) // (vtok + amount)
    return int(Decimal(gross) * (1 - FEE))


def buy_tokens(vsol: int, vtok: int, lamports: int) -> int:
    """Tokens recebidos ao gastar `lamports` na curva (a taxa de 1,25 % sai do valor bruto)."""
    if lamports <= 0 or vsol <= 0:
        return 0
    eff = int(Decimal(lamports) * (1 - FEE))
    return vtok - (vsol * vtok) // (vsol + eff)


def _open(name: str):
    p = HERE / name
    if p.exists():
        return open(p, newline="", encoding="utf-8")
    return gzip.open(HERE / (name + ".gz"), "rt", newline="", encoding="utf-8")


def load_tape(name: str):
    trades: dict[str, list] = {}
    with _open(name) as f:
        for r in csv.DictReader(f):
            r["bt"] = ts(r["block_time"])
            r["slot"] = int(r["slot"])
            r["ei"] = int(r["event_index"])
            r["sol"] = int(r["sol_lamports"])
            r["tok"] = int(Decimal(r["token_amount"]) * 10**6)
            trades.setdefault(r["mint"], []).append(r)
    for m in trades:
        trades[m].sort(key=lambda r: (r["slot"], r["signature"], r["ei"]))
    return trades


def load_snaps(name: str):
    snaps: dict[str, list] = {}
    with _open(name) as f:
        for r in csv.DictReader(f):
            snaps.setdefault(r["mint"], []).append(dict(
                t=ts(r["observed_at"]), src=r["source"],
                vsol=int(Decimal(r["virtual_sol_reserves"]) * 10**9),
                vtok=int(Decimal(r["virtual_token_reserves"]) * 10**6),
                slot=int(r["slot"] or 0)))
    for m in snaps:
        snaps[m].sort(key=lambda r: r["t"])
    return snaps


def load_real(name: str = "q1.csv"):
    out = []
    with _open(name) as f:
        for r in csv.DictReader(f):
            entry = _jload(r["entry_json"]) or {}
            exitj = _jload(r["exit_json"]) or {}
            params = _jload(r["params"]) or {}
            P = dict(
                pop="real", pid=r["position_id"], mint=r["mint"], sym=(r["symbol"] or "?").strip(),
                rule="%s/%s" % (r["rule_set"], r["rule_set_version"]),
                entry_at=ts(r["entry_at"]), exit_at=ts(r["exit_at"]),
                spent=int(r["sol_spent_lamports"]), received=int(r["sol_received_lamports"]),
                pnl_sol=Decimal(r["pnl_sol"]), reason=r["exit_reason"],
                tokens=int(Decimal(str(entry.get("token_amount", 0)))),
                entry_slot=int(entry.get("slot") or 0),
                entry_bt=ts(entry.get("block_time")) or ts(r["entry_at"]),
                vsol0=int(Decimal(str(entry.get("virtual_sol_reserves_after", 0)))),
                vtok0=int(Decimal(str(entry.get("virtual_token_reserves_after", 0)))),
                exit_slot=int(exitj.get("slot") or 0),
                size_sol=Decimal(str(params.get("size_sol", "0.07"))),
                target_x=Decimal(str(params.get("target_x", "1.15"))),
                trailing=Decimal(str(params.get("trailing_pct", "10"))) / 100,
                max_hold=int(params.get("max_hold_s", 300) or 300),
            )
            out.append(P)
    return out


def load_paper(name: str = "q4.csv"):
    out = []
    with _open(name) as f:
        for r in csv.DictReader(f):
            entry = _jload(r["entry_json"]) or {}
            snap = entry.get("snapshot") or {}
            params = _jload(r["params"]) or {}
            if not snap.get("virtual_sol_reserves"):
                continue
            spent = int(Decimal(str(entry.get("sol_spent", "0"))) * 10**9)
            P = dict(
                pop="paper", pid=r["id"], mint=r["mint"], sym=r["mint"][:6],
                rule="paper/%s" % (r["mode"] or "?"),
                entry_at=ts(r["entry_at"]), exit_at=ts(r["exit_at"]),
                spent=spent, received=0, pnl_sol=Decimal(r["pnl_sol"] or 0),
                reason=r["exit_reason"],
                tokens=int(Decimal(str(entry.get("tokens", "0"))) * 10**6),
                entry_slot=0,
                entry_bt=ts(snap.get("observed_at")) or ts(r["entry_at"]),
                vsol0=int(Decimal(str(snap["virtual_sol_reserves"])) * 10**9),
                vtok0=int(Decimal(str(snap["virtual_token_reserves"])) * 10**6),
                exit_slot=0,
                size_sol=Decimal(str(params.get("size_sol", "0") or 0)),
                target_x=Decimal(str(params.get("target_x", "1.15") or "1.15")),
                trailing=Decimal(str(params.get("trailing_pct", "10") or 10)) / 100,
                max_hold=int(params.get("max_hold_s", 300) or 300),
            )
            if P["tokens"] <= 0 or P["spent"] <= 0:
                continue
            out.append(P)
    return out


def build_path(P, trades, snaps):
    """Caminho "segurar": lista de (t, vsol, vtok, marca).

    Ancora = reservas do nosso fill de compra. Os nossos proprios trades sao saltados
    (a marca e contrafactual: o que a curva faria sem nos). Ressincronizacao por foto so
    com slot >= ultimo trade aplicado, como em R64/R65; na populacao de papel, onde o fill
    nao tem slot, a ancora e temporal (`block_time > entry_bt`).
    """
    tokens = P["tokens"]
    t0, s0 = P["entry_bt"], P["entry_slot"]
    if s0:
        T = [r for r in trades.get(P["mint"], []) if r["trader"] != OUR and r["slot"] > s0]
    else:
        T = [r for r in trades.get(P["mint"], []) if r["trader"] != OUR and r["bt"] > t0]
    S = [s for s in snaps.get(P["mint"], []) if s["t"] > t0]
    vsol, vtok = P["vsol0"], P["vtok0"]
    P["n_trades"] = len(T)
    P["resync_max_sol"] = 0.0
    P["clock_regressions"] = 0
    P["_tape_w"] = [r["bt"] for r in T]
    if not vsol or not vtok or not tokens:
        P["source"] = "none"
        P["path"] = []
        return []
    path = [(t0, vsol, vtok, sell_net(vsol, vtok, tokens))]
    if T:
        P["source"] = "tape+photos"
        anchor = s0 or T[0]["slot"]
        events = [(r["slot"], 0, r["bt"], r) for r in T] + \
                 [(s["slot"], 1, s["t"], s) for s in S if s["slot"] and s["slot"] >= anchor]
        events.sort(key=lambda e: (e[0], e[1], e[2]))
        last_slot = anchor
        for slot, kind, t, e in events:
            if kind == 0:
                if e["side"] == "buy":
                    vsol += e["sol"]
                    vtok -= e["tok"]
                else:
                    vsol -= e["sol"]
                    vtok += e["tok"]
                last_slot = slot
            else:
                if slot < last_slot:
                    continue
                P["resync_max_sol"] = max(P["resync_max_sol"], abs(e["vsol"] - vsol) / 1e9)
                vsol, vtok = e["vsol"], e["vtok"]
            if vsol <= 0 or vtok <= 0:
                break
            # Achado da Astra (R72): a cadeia avanca por slot, a observacao chega por relogio.
            # Reordenar estados prontos por timestamp faz o caminho VOLTAR a um slot antigo e
            # fabrica quedas. Aqui a ordem e a da cadeia e o carimbo e monotono nao-decrescente.
            stamp = max(t, path[-1][0])
            P["clock_regressions"] += 1 if t < path[-1][0] else 0
            path.append((stamp, vsol, vtok, sell_net(vsol, vtok, tokens)))
    else:
        P["source"] = "photos" if S else "none"
        for s in S:
            stamp = max(s["t"], path[-1][0])
            path.append((stamp, s["vsol"], s["vtok"], sell_net(s["vsol"], s["vtok"], tokens)))
    P["path"] = path
    return path


def window(P, seconds: int = WINDOW_S, tail_s: float = 0.0):
    """Pontos do caminho ate `seconds` s apos a entrada, mais `tail_s` s de cauda.

    A cauda existe porque um gatilho aos 300 s so pousa 1,6 s depois: sem ela, a saida
    seria liquidada pelo ultimo estado <= 300 s, o que e liquidacao retroativa (achado da
    Astra, R72 must-fix 1). Gatilhos continuam limitados a `seconds`.
    """
    end = P["entry_bt"] + timedelta(seconds=seconds + tail_s)
    return [p for p in P["path"] if p[0] <= end]


def coverage(P, seconds: int = WINDOW_S):
    """Diagnostico de cobertura: pontos na janela, maior buraco (s) e fonte."""
    W = window(P, seconds)
    P["n_points"] = len(W)
    t0 = P["entry_bt"]
    end = t0 + timedelta(seconds=seconds)
    P["n_tape_in_window"] = sum(1 for r in P.get("_tape_w", []) if t0 < r <= end)
    if len(W) < 2:
        P["max_gap_s"] = float(seconds)
        P["tape_span_s"] = 0.0
        return P
    gaps = [(W[i + 1][0] - W[i][0]).total_seconds() for i in range(len(W) - 1)]
    tail = (P["entry_bt"] + timedelta(seconds=seconds) - W[-1][0]).total_seconds()
    P["max_gap_s"] = max(gaps + [tail])
    P["tape_span_s"] = (W[-1][0] - W[0][0]).total_seconds()
    return P


def resolvable(P, seconds: int = WINDOW_S) -> bool:
    """So entra no censo quem tem fita DENTRO da janela.

    Fotos de ~15 s nao resolvem uma oscilacao de 3 % em 30 s. E ter fita "algures no
    caminho" nao basta: a Astra mostrou que 3 fotos na janela + 1 trade depois dela
    passariam por resolviveis. Exige-se `n_tape_in_window >= 3`.
    """
    return P["source"] == "tape+photos" and P.get("n_tape_in_window", 0) >= 3


def load_all():
    real = load_real()
    paper = load_paper()
    tr_real, sn_real = load_tape("q2.csv"), load_snaps("q3.csv")
    tr_paper, sn_paper = load_tape("q5.csv"), load_snaps("q6.csv")
    for P in real:
        build_path(P, tr_real, sn_real)
        coverage(P)
    for P in paper:
        build_path(P, tr_paper, sn_paper)
        coverage(P)
    return real, paper


if __name__ == "__main__":
    real, paper = load_all()
    for name, pop in (("real", real), ("paper", paper)):
        by_src: dict[str, int] = {}
        for P in pop:
            by_src[P["source"]] = by_src.get(P["source"], 0) + 1
        ok = [P for P in pop if resolvable(P)]
        gaps = sorted(P["max_gap_s"] for P in ok)
        print("%s: n=%d fontes=%s | resolviveis=%d | mediana do maior buraco=%.1f s" % (
            name, len(pop), by_src, len(ok), gaps[len(gaps) // 2] if gaps else -1))
