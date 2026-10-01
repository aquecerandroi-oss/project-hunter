"""R86 / H-027 — reconstrução causal de `razao_mm20d` e das covariáveis; população em unidades.

Puro e offline: lê os CSV exportados da VPS (`cache/daily_*.csv` e `cache/feat.csv`, cegos; `cache/out.csv`
com os desfechos, lido só depois do pré-registro) e devolve linhas para `stats86`/`run86`.

`razao_mm20d` = C_D ÷ média(C_{D−19}, …, C_D) − 1, com D = o último dia UTC completo antes da decisão
(D = data(obs) − 1: a vela 23:59 de D fecha em 00:00 de D+1 ≤ obs), C_d = fechamento da vela 1m final que abre
às 23:59 de d. Cada um dos 20 dias exige as 1 440 velas 1m finais e o fechamento 23:59; dia faltando ou
incompleto torna a medida **indisponível** (nunca interpolada). Guarda: a última chegada (`received_at`, carimbo
da primeira inserção — `ON CONFLICT DO NOTHING`, nunca reescrito) de cada dia tem de ser ≤ `emitted_at`.
O dia corrente (data(obs)) e os seguintes nunca são lidos.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from statistics import fmean

from infra.research.guards import Instants, check_observable

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
NDAYS = 20
FULL_DAY = 1440
WINDOW = 1440
MIN = timedelta(minutes=1)
STRATS = ("momentum", "volume_anomaly")
T0 = datetime(2026, 9, 6, tzinfo=UTC)
AS_OF = datetime(2026, 10, 1, tzinfo=UTC)
"""Janela de emissão congelada (emenda 03:02Z): [T0, AS_OF)."""


@dataclass(frozen=True)
class Day:
    n_final: int
    max_recv: datetime
    close_2359: Decimal | None


def ts(text: str | None) -> datetime | None:
    text = (text or "").strip()
    if not text:
        return None
    if text.endswith("+00"):
        text += ":00"
    value = datetime.fromisoformat(text.replace(" ", "T"))
    if value.tzinfo is None:
        raise ValueError(f"instante sem fuso no export: {text!r}")
    return value.astimezone(UTC)


def dec(text: str | None) -> Decimal | None:
    text = (text or "").strip()
    return None if text == "" else Decimal(text)


def _aware(*xs: datetime) -> None:
    for x in xs:
        if x.tzinfo is None:
            raise ValueError("datetime ingênuo recusado (UTC aware obrigatório)")


def window_days(obs: datetime) -> list[date]:
    last = obs.astimezone(UTC).date() - timedelta(days=1)
    return [last - timedelta(days=NDAYS - 1 - i) for i in range(NDAYS)]


def razao_mm20d(days: Mapping[date, Day], obs: datetime, emitted: datetime, guard: bool = True
                ) -> tuple[float | None, str | None]:
    """(valor, None) ou (None, motivo). Lê só os 20 dias anteriores a data(obs)."""
    _aware(obs, emitted)
    closes: list[Decimal] = []
    late = False
    for d in window_days(obs):
        day = days.get(d)
        if day is None or day.n_final != FULL_DAY or day.close_2359 is None:
            return None, "dia_incompleto"
        late = late or day.max_recv > emitted
        closes.append(day.close_2359)
    if guard and late:
        return None, "chegou_depois"
    mean = sum(closes, Decimal(0)) / NDAYS
    return float(closes[-1] / mean - 1), None


def cheat_razao_same_day(days: Mapping[date, Day], obs: datetime) -> float:
    """TRAPAÇA deliberada (só para o teste de vazamento): janela termina no dia corrente."""
    d0 = obs.date()
    closes = [days[d0 - timedelta(days=i)].close_2359 for i in range(NDAYS)]
    assert all(c is not None for c in closes)
    return float(closes[0] / (sum(closes, Decimal(0)) / NDAYS) - 1)  # type: ignore[operator, arg-type]


def load_daily(paths: Iterable[Path] | None = None) -> dict[str, dict[date, Day]]:
    out: dict[str, dict[date, Day]] = defaultdict(dict)
    for p in paths or sorted(CACHE.glob("daily_*.csv")):
        with p.open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                recv = ts(r["max_recv"])
                assert recv is not None
                out[r["market_id"]][date.fromisoformat(r["day"])] = Day(int(r["n_final"]), recv, dec(r["close_2359"]))
    return dict(out)


def eligible(raw: Mapping[str, object]) -> bool:
    """População congelada: Binance, perpétuo, coorte prospectiva, terminal, emissão em [T0, AS_OF)."""
    t = raw["emitted_at"]
    assert isinstance(t, datetime)
    _aware(t)
    return (raw["exchange"] == "binance" and raw["market_type"] == "perpetual"
            and raw["cohort"] == "prospective" and raw["tracking_state"] == "terminal" and T0 <= t < AS_OF)


def load_markets(path: Path | None = None) -> dict[str, str]:
    with (path or CACHE / "markets.csv").open(newline="", encoding="utf-8") as fh:
        return {r["market_id"]: r["exchange"] for r in csv.DictReader(fh)}


def _window_ok(n: int, first: datetime | None, last: datetime | None, obs: datetime) -> bool:
    return n == WINDOW and first == obs - WINDOW * MIN and last == obs - MIN


def feature_rows(daily: Mapping[str, Mapping[date, Day]], path: Path | None = None) -> tuple[list[dict], Counter]:
    """Export cego → linhas (sem desfecho). Só perpétuos e estado `terminal`; o resto contado."""
    rows, cnt = [], Counter()
    exchanges = load_markets()
    with (path or CACHE / "feat.csv").open(newline="", encoding="utf-8") as fh:
        for raw in csv.DictReader(fh):
            key = raw["strategy"] if raw["strategy"] in STRATS else "mean_reversion_v14"
            if raw["market_type"] != "perpetual":
                cnt[(key, "fora_spot")] += 1
                continue
            if raw["tracking_state"] != "terminal":
                cnt[(key, "fora_" + (raw["tracking_state"] or "sem_outcome"))] += 1
                continue
            obs, emitted = ts(raw["obs"]), ts(raw["emitted_at"])
            assert obs is not None and emitted is not None
            if not eligible({**raw, "emitted_at": emitted, "exchange": exchanges.get(raw["market_id"])}):
                cnt[(key, "fora_janela_ou_exchange")] += 1
                continue
            n = int(raw["n"] or 0)
            first, last, recv = ts(raw["first_open"]), ts(raw["last_open"]), ts(raw["max_recv"])
            close, lo, c240 = dec(raw["close_last"]), dec(raw["lo24"]), dec(raw["close_m240"])
            ok = _window_ok(n, first, last, obs) and close is not None
            d_low = float((close - lo) / lo) if ok and lo and lo > 0 else None  # type: ignore[operator]
            ret4h = float(close / c240 - 1) if close is not None and c240 and c240 > 0 else None
            atr = dec(raw["env_atr_pct"])
            razao, why = razao_mm20d(daily.get(raw["market_id"], {}), obs, emitted)
            razao_ng, _ = razao_mm20d(daily.get(raw["market_id"], {}), obs, emitted, guard=False)
            rows.append({
                "signal_id": raw["signal_id"], "strategy": key, "version": raw["version"],
                "market": raw["market_id"], "symbol": raw["symbol"], "obs": obs, "t": emitted,
                "day": obs.date().isoformat(), "has_r": raw["has_r"] == "t",
                "r_net_reason": raw["r_net_reason"] or None,
                "razao": razao, "razao_why": why, "razao_noguard": razao_ng,
                "d_low": d_low, "ret4h": ret4h, "atr_pct": None if atr is None else float(atr),
                "as_of": obs, "computed_at": recv if recv is not None else obs,
            })
    return rows, cnt


def guard_window(rows: list[dict]) -> tuple[list[dict], int]:
    """Guarda do moinho na janela de 24 h (como no R83): vela persistida depois do sinal = recusa."""
    kept, refused = [], 0
    for r in rows:
        if check_observable(Instants(r["as_of"], r["computed_at"]), r["t"], str(r["signal_id"])) is None:
            kept.append(r)
        else:
            refused += 1
    return kept, refused


class JoinError(ValueError):
    """Junção com desfechos inconsistente: o rótulo não é emitido (revisão da Astra no resultado)."""


def attach_outcomes(rows: list[dict], path: Path | None = None) -> None:
    out = {}
    with (path or CACHE / "out.csv").open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["signal_id"] in out:
                raise JoinError(f"signal_id repetido nos desfechos: {r['signal_id']}")
            out[r["signal_id"]] = (dec(r["r_multiple"]), dec(r["r_ex_funding"]))
    for row in rows:
        rn, rx = out.get(row["signal_id"], (None, None))
        row["r"] = None if rn is None else float(rn)
        row["r_ex"] = None if rx is None else float(rx)


def units(rows: list[dict], outcome: str = "r") -> list[dict]:
    """Uma unidade por (estratégia, mercado, obs): média do desfecho e do ATR% das versões com desfecho."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get(outcome) is not None:
            groups[(r["strategy"], r["market"], r["obs"])].append(r)
    out = []
    for (strat, mkt, obs), g in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][2], kv[0][1])):
        atrs = [r["atr_pct"] for r in g if r["atr_pct"] is not None]
        head = g[0]
        out.append({
            "strategy": strat, "market": mkt, "obs": obs, "day": obs.date().isoformat(),
            "r": fmean(r[outcome] for r in g), "atr_pct": fmean(atrs) if atrs else None,
            "razao": head["razao"], "d_low": head["d_low"], "ret4h": head["ret4h"],
            "n_versions": len(g), "versions": sorted({r["version"] for r in g}),
        })
    return out


def check_join(rows: list[dict], eligible: set[str]) -> None:
    """Todo elegível congelado tem de estar nas features e ter R_net agora; senão não há rótulo."""
    seen = {r["signal_id"]: r for r in rows}
    missing = sorted(eligible - seen.keys())
    nulled = sorted(s for s in eligible if s in seen and seen[s].get("r") is None)
    if missing or nulled:
        raise JoinError(f"elegíveis ausentes {len(missing)} · sem R_net agora {len(nulled)}")
