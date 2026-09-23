"""R75 — carregador da H-013: o indicador `equilibrio` lido do que a porta GRAVOU.

As três grandezas vêm de `meme_proposals.reasons` (bloco `flow`: `buys_1m`, `sells_1m`,
`net_sol_flow_1m`; e `curve_progress_pct`), escritas no instante da decisão. Não se lê
`meme_trades` (cópia por polling, ~44 s de atraso — R73/KB-0153). Não há fita a
reconstruir, logo não há por onde entrar futuro: a feature é a que a porta usou.

Dinheiro em `Decimal`; o retorno (`ret`) sai em float só para a estatística.
Regras fixadas ANTES de olhar desfechos:
- sem compras e sem vendas → razão indefinida (linha censurada); sem compras e com
  vendas → razão infinita (conta como ≥ 0,6);
- qualquer das três ausente → `equilibrio` indefinido (censurado, contado na cobertura);
- uma decisão por mint: a real ganha da de papel; entre iguais, a mais antiga
  (`decided_at`, desempate por `bet_id`) — a regra congelada no R73.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

HERE = Path(__file__).resolve().parent
Row = dict[str, object]


@dataclass(frozen=True)
class Thresholds:
    ratio: float  # vendas ÷ compras ≥ ratio
    flow: Decimal  # fluxo líquido do minuto < flow (SOL)
    progress: Decimal  # progresso da curva < progress (%)


FROZEN = Thresholds(ratio=0.6, flow=Decimal("2"), progress=Decimal("25"))


def _dec(x: object) -> Decimal | None:
    if x is None or str(x).strip() == "":
        return None
    try:
        return Decimal(str(x))
    except InvalidOperation:
        return None


def _ts(x: object) -> datetime | None:
    s = str(x or "").strip()
    if not s:
        return None
    if s.endswith("+00"):
        s += ":00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        raise ValueError(f"instante sem fuso: {s!r}")
    return dt.astimezone(UTC)


def _ratio(buys: object, sells: object) -> float | None:
    if buys is None or sells is None:
        return None
    b, s = int(str(buys)), int(str(sells))
    if b == 0:
        return None if s == 0 else float("inf")
    return s / b


def parse(raw: dict[str, str]) -> Row:
    flow = json.loads(raw["flow_json"]) if raw.get("flow_json") else None
    dec = _ts(raw["decided_at"])
    entry, exit_ = _ts(raw.get("entry_at")), _ts(raw.get("exit_at"))
    size, pnl = _dec(raw.get("size_sol")), _dec(raw.get("pnl_sol"))
    assert dec is not None
    return {
        "lane": raw["lane"], "bet_id": raw["bet_id"], "mint": raw["mint"],
        "symbol": raw.get("symbol") or "", "rule_set": raw["rule_set"],
        "gate": raw.get("gate") or "", "series": raw.get("series") or "",
        "decided_at": dec, "dia": dec.date().isoformat(), "hora": dec.strftime("%Y-%m-%dT%H"),
        "exit_reason": raw.get("exit_reason") or "",
        "has_flow": flow is not None,
        "buys": None if flow is None else flow.get("buys_1m"),
        "sells": None if flow is None else flow.get("sells_1m"),
        "ratio": None if flow is None else _ratio(flow.get("buys_1m"), flow.get("sells_1m")),
        "net_flow": None if flow is None else _dec(flow.get("net_sol_flow_1m")),
        "cap_ratio": None if flow is None else _dec(flow.get("max_sells_to_buys")),
        "progress": _dec(raw.get("progress_pct")),
        "size_sol": size, "pnl_sol": pnl,
        "ret": float(pnl / size) if pnl is not None and size else None,
        "hold_s": (exit_ - entry).total_seconds() if entry and exit_ else None,
    }


def features(r: Row, t: Thresholds) -> dict[str, bool | None]:
    ratio, net, prog = r["ratio"], r["net_flow"], r["progress"]
    c_ratio = None if ratio is None else float(ratio) >= t.ratio  # type: ignore[arg-type]
    c_flow = None if net is None else net < t.flow  # type: ignore[operator]
    c_prog = None if prog is None else prog < t.progress  # type: ignore[operator]
    parts = (c_ratio, c_flow, c_prog)
    eq = None if any(p is None for p in parts) else all(parts)
    return {"c_ratio": c_ratio, "c_flow": c_flow, "c_prog": c_prog, "equilibrio": eq}


def equilibrio(r: Row, t: Thresholds = FROZEN) -> bool | None:
    return features(r, t)["equilibrio"]


def one_per_mint(rows: Iterable[Row]) -> list[Row]:
    best: dict[str, Row] = {}

    def key(r: Row) -> tuple[int, datetime, str]:
        return (0 if r["lane"] == "live" else 1, r["decided_at"], str(r["bet_id"]))  # type: ignore[return-value]

    for r in rows:
        m = str(r["mint"])
        if m not in best or key(r) < key(best[m]):
            best[m] = r
    return sorted(best.values(), key=lambda r: r["decided_at"])  # type: ignore[arg-type, return-value]


def load(path: Path = HERE / "pop.csv") -> list[Row]:
    """Todas as linhas: posições reais (qualquer porta) + papel da `fluxo_e_holders`."""
    with path.open(encoding="utf-8", newline="") as f:
        return [parse(raw) for raw in csv.DictReader(f)]


def population(rows: Iterable[Row], t: Thresholds = FROZEN) -> tuple[list[Row], list[Row]]:
    """(usadas, censuradas): escolhe UMA decisão por mint primeiro, só depois censura.

    Ordem exigida pela Astra: censurar antes deixava o papel substituir a real censurada.
    """
    chosen = one_per_mint(r for r in rows if str(r["gate"]).startswith("fluxo_e_holders/"))
    kept = [r for r in chosen if in_population(r) and features(r, t)["equilibrio"] is not None]
    ids = {id(r) for r in kept}
    return kept, [r for r in chosen if id(r) not in ids]


def in_population(r: Row) -> bool:
    """A população da H-013: porta `fluxo_e_holders`, bloco `flow` presente, fechada."""
    return (
        str(r["gate"]).startswith("fluxo_e_holders/")
        and bool(r["has_flow"])
        and r["ret"] is not None
    )
