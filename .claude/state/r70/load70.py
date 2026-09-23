"""R70 — carregadores das populações da fila de hipóteses. Puros, offline, sem relógio.

Cada função devolve `list[dict]` já no formato que `infra.research.protocol` consome:
instantes `datetime` UTC *aware*, ausente continua ausente (nunca vira zero), e as
colunas de observabilidade (`as_of`, `computed_at`, `tape_as_of`) vêm da própria linha
exportada — é a guarda de `infra/research/guards.py` que as confere, não este módulo.

Fontes (somente-leitura, exportadas da VPS com COPY TO STDOUT):
  `lab.csv`  — sinais terminais do Lab (2026-09-06 19:00 UTC em diante) com r_multiple,
               o envelope do sinal (`env_*`), o `feature_snapshots` mais recente
               observável na decisão (`snap_*`, `mom15`, `ret4h`, `rv5`) e o agregado
               de 5 velas de 1 min `is_final` fechadas antes da decisão (`nbars`,
               `taker_buy`, `vol`, `last_close`, `max_recv`);
  `ret.csv`  — `virtual_entry`/`exit_price`/`direction` dos mesmos sinais, para o
               desfecho em "% líquido por operação" que o H-006 pré-registou;
  `pct.csv`  — export do R69 (percentis dentro da coorte viva);
  `inst.csv` — os instantes (`as_of`, `computed_at`, `tape_as_of`) da linha de feature
               que o R69 usou por mint, para a guarda poder correr sobre o H-004.
"""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
R69 = HERE.parent / "r69"

COST_ROUNDTRIP = Decimal("0.0014")
"""Custo de ida-e-volta medido do lado à vista (R68): 0,14 % por operação."""


def _dt(text: str) -> datetime | None:
    """`timestamptz` do Postgres → `datetime` UTC aware. Vazio continua ausente."""
    text = (text or "").strip()
    if not text:
        return None
    value = datetime.fromisoformat(text.replace(" ", "T"))
    if value.tzinfo is None:
        raise ValueError(f"instante sem fuso no export: {text!r}")
    return value.astimezone(timezone.utc)


def _f(text: str) -> float | None:
    text = (text or "").strip()
    if not text:
        return None
    return float(text)


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _day(instant: datetime) -> str:
    return instant.date().isoformat()


# --------------------------------------------------------------------------- H-004


def h004_rows(*, min_cohort: int = 20) -> list[dict[str, object]]:
    """Decisões do Lab meme com coorte viva de ≥ `min_cohort` mints observáveis.

    O percentil e o desfecho vêm do export do R69; os instantes da linha de feature do
    sujeito vêm de `inst.csv` e são casados por `(mint, as_of)` — se não casarem, a
    linha fica **sem** instantes e a guarda recusa-a (nunca se inventa um instante).
    """
    instants = {
        (r["mint"], _dt(r["as_of"])): r for r in _rows(HERE / "inst.csv")
    }
    out: list[dict[str, object]] = []
    for row in _rows(R69 / "pct.csv"):
        cohort = _f(row["cohort_n"])
        if cohort is None or cohort < min_cohort:
            continue
        decision = _dt(row["t"])
        as_of = _dt(row["subj_as_of"])
        assert decision is not None and as_of is not None
        inst = instants.get((row["mint"], as_of))
        if inst is None:
            continue
        size = Decimal(row["size_sol"])
        pnl = Decimal(row["pnl_sol"])
        out.append(
            {
                "mint": row["mint"],
                "t": decision,
                "dia": _day(decision),
                "hora": decision.strftime("%Y-%m-%dT%H"),
                "ret": float(pnl / size),
                "pnl_sol": str(pnl),
                "p_sb": _f(row["p_sb"]),
                "as_of": as_of,
                "computed_at": _dt(inst["computed_at"]),
                "tape_as_of": _dt(inst["tape_as_of"]),
            }
        )
    return out


# ------------------------------------------------------- populações do Lab (spot)


def _lab_base() -> list[dict[str, object]]:
    """Os sinais terminais com desfecho medido, já com as duas unidades de desfecho."""
    prices = {r["signal_id"]: r for r in _rows(HERE / "ret.csv")}
    out: list[dict[str, object]] = []
    for row in _rows(HERE / "lab.csv"):
        decision = _dt(row["t"])
        assert decision is not None
        price = prices.get(row["signal_id"], {})
        entry, exit_ = _f(price.get("virtual_entry", "")), _f(price.get("exit_price", ""))
        side = 1.0 if price.get("dir") == "long" else -1.0
        ret_net = (
            None
            if entry is None or exit_ is None or entry <= 0
            else side * (exit_ / entry - 1.0) - float(COST_ROUNDTRIP)
        )
        day = _day(decision)
        out.append(
            {
                "signal_id": row["signal_id"],
                "mercado": row["symbol"],
                "t": decision,
                "dia": day,
                "bloco3d": _block3d(decision),
                "r": _f(row["r_multiple"]),
                "ret_net": ret_net,
                "env_vr5": _f(row["env_vr5"]),
                "mom15": _f(row["mom15"]),
                "ret4h": _f(row["ret4h"]),
                "rv5": _f(row["rv5"]),
                "env_ret4h": _f(row["env_ret4h"]),
                "snap_as_of": _dt(row["snap_as_of"]),
                "snap_computed_at": _dt(row["snap_computed_at"]),
                "snap_tape": _dt(row["snap_tape"]),
                "taker_imb": _taker(row),
                "bar_close": _dt(row["last_close"]),
                "bar_recv": _dt(row["max_recv"]),
            }
        )
    return out


def _block3d(instant: datetime) -> str:
    """Rótulo do bloco de 3 dias (R68), ancorado numa época fixa — não no relógio."""
    epoch = datetime(2026, 1, 1, tzinfo=timezone.utc)
    index = (instant - epoch) // timedelta(days=3)
    return f"b{index:04d}"


def _taker(row: dict[str, str]) -> float | None:
    """`taker_buy_volume / volume` sobre as **5** velas de 1 min completas antes da decisão.

    Menos de 5 barras é ausente (a hipótese é sobre a barra de 5 min, e uma barra
    incompleta é outra população), volume nulo é ausente.
    """
    if row["nbars"] != "5":
        return None
    buy, vol = _f(row["taker_buy"]), _f(row["vol"])
    if buy is None or vol is None or vol <= 0:
        return None
    return buy / vol


def h005_rows() -> list[dict[str, object]]:
    """Decisões do Lab com `momentum_15m` observável (do `feature_snapshots`)."""
    return [r for r in _lab_base() if r["r"] is not None and r["snap_as_of"] is not None]


def h006_rows() -> list[dict[str, object]]:
    """Decisões do Lab com as 5 velas de 1 min completas e o desfecho líquido."""
    return [
        r for r in _lab_base() if r["ret_net"] is not None and r["bar_close"] is not None
    ]


def h007_rows(*, floor: float = 4.0) -> list[dict[str, object]]:
    """Decisões do Lab **acima do piso de volume atual (4×)**, com `volume_ratio_5m`.

    O piso é o da própria mesa; o contraste do H-007 é sobre o **teto**, por isso a
    linha abaixo de 4× sai da população (e não vira um braço "baixo" artificial).
    """
    return [
        r
        for r in _lab_base()
        if r["r"] is not None and r["env_vr5"] is not None and float(r["env_vr5"]) >= floor
    ]


def h008_envelope_rows() -> list[dict[str, object]]:
    """A população **verbatim** do H-008: `return_4h` presente no envelope do sinal."""
    return [r for r in _lab_base() if r["r"] is not None and r["env_ret4h"] is not None]


def h008_snapshot_rows() -> list[dict[str, object]]:
    """Desvio declarado: `return_4h` do `feature_snapshots` observável na decisão."""
    return [r for r in _lab_base() if r["r"] is not None and r["snap_as_of"] is not None]
