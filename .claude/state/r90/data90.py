"""R90 / H-033 — OI em nível relativo à própria semana; guardas causais; população em unidades.

Puro e offline: lê `cache/feat.csv` (export cego da VPS, `q_feat.sql`) e, depois do pré-registro, `cache/out.csv`.

`oi_rel7d` = ln(OI corrente) − mediana(ln OI) na janela de 7 dias que termina na leitura corrente, com
**OI corrente** = a amostra de `open_interest_history` de maior bucket ≤ obs − 15 min (folga `LAG`). O bucket
é o piso de 5 min do início da rodada de leitura, não o instante da leitura (`hunter_strategy_worker.derivatives`);
no outbox (26/09 → 07/10) a maior distância bucket → inserção medida foi 325 s (`lag.txt`), então 15 min é a folga
declarada. Quando o outbox ainda guarda o evento da leitura usada, a guarda de chegada real roda (inserção ≤ obs).
Indisponível (nunca zero): leitura ausente, mais velha que obs − 25 min, janela com < 90 % dos 2 016 buckets.
Direção da hipótese: OI alto (lotado) rende menos → a variável testada é x = −oi_rel7d (favorável = alto).
"""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import fmean, median

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
LAG = timedelta(minutes=15)
MAX_STALE = timedelta(minutes=10)
WINDOW = timedelta(days=7)
SLOTS = 2016
MIN_COVER = 0.90
STRATS = ("momentum", "volume_anomaly")
DESCR = ("mean_reversion", "mean_reversion_h1")


@dataclass(frozen=True)
class Oi:
    ts: datetime
    open_interest: float


def _aware(*xs: datetime) -> None:
    for x in xs:
        if x.tzinfo is None:
            raise ValueError("datetime ingênuo recusado (UTC aware obrigatório)")


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


def fl(text: str | None) -> float | None:
    text = (text or "").strip()
    return None if text == "" else float(text)


def oi_reason(*, oi_ts: datetime | None, oi_cur: float | None, n_win: int | None, created: datetime | None,
              obs: datetime, lag: timedelta = LAG) -> str | None:
    """Motivo de indisponibilidade da leitura de OI, ou None. A ordem é a do relatório."""
    if oi_ts is None or oi_cur is None or oi_cur <= 0:
        return "oi_ausente"
    if oi_ts > obs - lag:
        return "oi_dentro_da_folga"
    if oi_ts < obs - lag - MAX_STALE:
        return "oi_velho"
    if n_win is None or n_win < MIN_COVER * SLOTS:
        return "oi_janela_curta"
    if created is not None and created > obs:
        return "oi_chegou_depois"
    return None


def oi_rel7d_from_history(history: list[Oi], obs: datetime) -> tuple[float | None, str | None]:
    """Mesma definição do SQL, a partir das amostras cruas (caminho da réplica e dos testes)."""
    _aware(obs, *(h.ts for h in history[:1]))
    usable = [h for h in history if h.ts <= obs - LAG]
    if not usable:
        return None, "oi_ausente"
    cur = max(usable, key=lambda h: h.ts)
    win = [h for h in usable if cur.ts - WINDOW < h.ts <= cur.ts and h.open_interest > 0]
    why = oi_reason(oi_ts=cur.ts, oi_cur=cur.open_interest, n_win=len(win), created=None, obs=obs)
    if why:
        return None, why
    return math.log(cur.open_interest) - median(math.log(h.open_interest) for h in win), None


def cheat_oi_rel_no_slack(history: list[Oi], obs: datetime) -> float:
    """TRAPAÇA deliberada (só para a sonda de vazamento): leitura corrente = bucket ≤ obs, sem folga."""
    usable = [h for h in history if h.ts <= obs]
    cur = max(usable, key=lambda h: h.ts)
    win = [h for h in usable if cur.ts - WINDOW < h.ts <= cur.ts]
    return math.log(cur.open_interest) - median(math.log(h.open_interest) for h in win)


def oi_vol(oi_cur: float | None, close: float | None, qv24: float | None, n_qv: int) -> float | None:
    """Secundária: ln(OI × preço ÷ volume de cotação de 24 h), velas 1m finais completas."""
    if oi_cur is None or close is None or qv24 is None or n_qv != 1440 or qv24 <= 0 or oi_cur <= 0:
        return None
    return math.log(oi_cur * close / qv24)


def row_from_csv(raw: dict[str, str], lag: timedelta = LAG) -> dict:
    obs, emitted = ts(raw["obs"]), ts(raw["emitted_at"])
    assert obs is not None and emitted is not None
    close, lo, c240 = fl(raw["close_last"]), fl(raw["lo24"]), fl(raw["close_m240"])
    oi_cur, med = fl(raw["oi_cur"]), fl(raw["med_ln_oi"])
    created = ts(raw["oi_created_at"])
    dispatched = ts(raw.get("oi_dispatched_at"))
    why: str | None = None
    if int(raw["n"] or 0) != 1440 or close is None or c240 is None or not lo or lo <= 0:
        why = "velas_incompletas"
    else:
        recv = ts(raw["max_recv"])
        if recv is None or recv > emitted:
            why = "velas_chegaram_depois"
    if why is None and fl(raw["env_atr_pct"]) is None:
        why = "sem_atr"
    if why is None:
        why = oi_reason(oi_ts=ts(raw["oi_ts"]), oi_cur=oi_cur, n_win=int(raw["n_win"]) if raw["n_win"] else None,
                        created=created, obs=obs, lag=lag)
    if why is None and med is None:
        why = "oi_janela_curta"
    ok = why is None
    rel = math.log(oi_cur) - med if ok and oi_cur and med is not None else None  # type: ignore[operator]
    return {
        "signal_id": raw["signal_id"], "strategy": raw["strategy"], "version": raw["version"],
        "market": raw["market_id"], "symbol": raw["symbol"], "obs": obs, "t": emitted,
        "day": obs.date().isoformat(), "has_r": raw["has_r"] == "t", "why": why,
        "oi_rel": rel, "x": None if rel is None else -rel,
        "d_low": close / lo - 1 if ok else None,  # type: ignore[operator]
        "ret4h": close / c240 - 1 if ok else None,  # type: ignore[operator]
        "atr_pct": fl(raw["env_atr_pct"]) if ok else None,
        "oi_vol": oi_vol(oi_cur, close, fl(raw["qv24"]), int(raw["n_qv"] or 0)) if ok else None,
        "verified": dispatched is not None and dispatched <= obs,  # prova pós-commit (despacho do relay)
        "late_candles": int(raw.get("n_late") or 0) > 0,
        "oi_ts": ts(raw["oi_ts"]),
    }


def load_rows(path: Path | None = None, lag: timedelta = LAG) -> list[dict]:
    with (path or CACHE / "feat.csv").open(newline="", encoding="utf-8") as fh:
        return [row_from_csv(r, lag) for r in csv.DictReader(fh)]


class JoinError(ValueError):
    """Junção com desfechos inconsistente: o rótulo não é emitido."""


def attach_outcomes(rows: list[dict], path: Path | None = None) -> None:
    out: dict[str, tuple[float | None, float | None]] = {}
    with (path or CACHE / "out.csv").open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["signal_id"] in out:
                raise JoinError(f"signal_id repetido nos desfechos: {r['signal_id']}")
            out[r["signal_id"]] = (fl(r["r_multiple"]), fl(r["r_ex_funding"]))
    for row in rows:
        row["r"], row["r_ex"] = out.get(row["signal_id"], (None, None))


def check_join(rows: list[dict], eligible: set[str]) -> None:
    ids = [r["signal_id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise JoinError("signal_id repetido nas features")
    seen = {r["signal_id"]: r for r in rows}
    missing = sorted(eligible - seen.keys())
    nulled = sorted(s for s in eligible if s in seen and seen[s].get("r") is None)
    if missing or nulled:
        raise JoinError(f"elegíveis ausentes {len(missing)} · sem R_net agora {len(nulled)}")


def window_evidence(ev: dict[datetime, tuple[datetime, datetime]], cur: datetime, obs: datetime,
                    outbox_start: datetime, used: set[datetime] | None = None) -> tuple[bool, bool]:
    """(alguma amostra da janela inserida depois de obs, janela inteira provada pós-commit antes de obs).

    ev: bucket -> (última inserção, último despacho) do outbox para o mercado. `used`: os buckets que a mediana
    de fato usou (do OI cru); sem essa lista a janela nunca é certificada. Provada = a janela (cur - 7 d, cur]
    começa depois do início do outbox e TODO bucket usado tem evento com despacho <= obs.
    """
    _aware(cur, obs, outbox_start)
    inside = [(b, v) for b, v in ev.items() if cur - WINDOW < b <= cur]
    late = any(c > obs for _, (c, _) in inside)
    proven = (used is not None and cur - WINDOW >= outbox_start and not late and len(used) >= MIN_COVER * SLOTS
              and all(b in ev and ev[b][1] <= obs for b in used))
    return late, proven


def load_ev(path: Path | None = None) -> tuple[dict[str, dict[datetime, tuple[datetime, datetime]]], datetime]:
    """Eventos crus do outbox → por (símbolo, bucket): (maior inserção, maior despacho); início = menor inserção.
    Evento sem despacho conta como nunca provado (despacho = datetime.max)."""
    never = datetime.max.replace(tzinfo=UTC)
    out: dict[str, dict[datetime, tuple[datetime, datetime]]] = defaultdict(dict)
    first: datetime | None = None
    with (path or CACHE / "ev_raw.csv").open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            b, c = ts(r["b"]), ts(r["created_at"])
            assert b is not None and c is not None
            d = ts(r["dispatched_at"]) or never
            prev = out[r["symbol"]].get(b)
            out[r["symbol"]][b] = (c, d) if prev is None else (max(prev[0], c), max(prev[1], d))
            first = c if first is None or c < first else first
    assert first is not None
    return dict(out), first


def units(rows: list[dict], outcome: str = "r", var: str = "x") -> list[dict]:
    """Uma unidade por (estratégia, mercado, obs): média do desfecho e do ATR% das versões com desfecho."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get(outcome) is not None and r.get(var) is not None:
            groups[(r["strategy"], r["market"], r["obs"])].append(r)
    out = []
    for (strat, mkt, obs), g in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][2], kv[0][1])):
        head = g[0]
        out.append({
            "strategy": strat, "market": mkt, "obs": obs, "day": obs.date().isoformat(), "t": head["t"],
            "r": fmean(r[outcome] for r in g), "atr_pct": fmean(r["atr_pct"] for r in g),
            "x": head[var], "d_low": head["d_low"], "ret4h": head["ret4h"], "verified": head["verified"],
            "n_versions": len(g), "versions": sorted({r["version"] for r in g}),
        })
    return out
