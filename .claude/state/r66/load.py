"""R66 - serie de preco POS-GRADUACAO a partir do board 'graduated' (cadencia 60 s).

Por que o board e nao a fita: `meme_trades` com `program='pump_amm'` cobre so 1 002 dos
6 389 mints migrados em 7 dias e morre numa mediana de 57 s depois da migracao (o poller
`swap_api` so segue mints na watchlist do radar). O board `graduated` cobre 4 472 mints,
cadencia 60 s, ate ~1 h. Ver notes-R66.md S1.

Preco = market cap. O supply da pump.fun e fixo (1 000 000 000), logo
`market_cap_usd / supply` e o preco e QUALQUER RAZAO de market caps do mesmo mint e a
razao de precos. Para tirar a deriva SOL/USD da janela, converto tudo para SOL com a
serie global SOL/USD reconstruida de `volume_usd / volume_sol` (mediana por minuto de
parede sobre todos os mints daquele minuto).

Nao-antecipacao: o instante da decisao e `observed_at` da PRIMEIRA leitura do board em
ou depois de `migrated_at`; nada antes desse instante entra no caminho, e nenhuma
estatistica usa leitura posterior ao instante julgado.
"""

from __future__ import annotations

import csv
import statistics
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

csv.field_size_limit(10_000_000)

HERE = Path(__file__).resolve().parent
BRT = timezone(timedelta(hours=-3))


def ts(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    if s.endswith("+00"):
        s += ":00"
    return datetime.fromisoformat(s.replace(" ", "T"))


def dec(s: str) -> Decimal | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return Decimal(s)
    except Exception:
        return None


def load_tokens(path: str = "tokens.csv") -> dict[str, dict]:
    out: dict[str, dict] = {}
    with open(HERE / path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[r["mint"]] = dict(
                mint=r["mint"],
                symbol=(r.get("symbol") or "?").strip(),
                creator=r["creator"],
                created_at=ts(r["created_at"]),
                completed_at=ts(r["completed_at"]),
                migrated_at=ts(r["migrated_at"]),
                pool_created_at=ts(r["pool_created_at"]),
                total_supply=dec(r["total_supply"]),
                first_seen_source=r["first_seen_source"],
                has_twitter=r["has_twitter"] == "t",
            )
    return out


def _sol_usd_series(rows: list[dict]) -> dict[datetime, Decimal]:
    """SOL/USD por minuto de parede: mediana de volume_usd/volume_sol de todos os mints."""
    buckets: dict[datetime, list[float]] = {}
    for r in rows:
        vs, vu = r["volume_sol"], r["volume_usd"]
        if not vs or not vu or vs <= 0:
            continue
        rate = float(vu / vs)
        if not (20.0 < rate < 2000.0):  # lixo obvio
            continue
        key = r["observed_at"].replace(second=0, microsecond=0)
        buckets.setdefault(key, []).append(rate)
    return {k: Decimal(str(statistics.median(v))) for k, v in buckets.items()}


def load_board(tokens: dict[str, dict], path: str = "board.csv") -> dict[str, list[dict]]:
    raw: list[dict] = []
    with open(HERE / path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            raw.append(
                dict(
                    mint=r["mint"],
                    observed_at=ts(r["observed_at"]),
                    migrated_at=ts(r["migrated_at"]),
                    position=int(r["position"]) if r["position"] else None,
                    mcap_usd=dec(r["market_cap_usd"]),
                    ath_usd=dec(r["ath_market_cap_usd"]),
                    volume_sol=dec(r["volume_sol"]),
                    volume_usd=dec(r["volume_usd"]),
                    volume_5m_sol=dec(r["volume_5m_sol"]),
                    volume_1h_sol=dec(r["volume_1h_sol"]),
                    txs=int(r["txs"]) if r["txs"] else None,
                    buys=int(r["buys"]) if r["buys"] else None,
                    sells=int(r["sells"]) if r["sells"] else None,
                    holders=int(r["holders"]) if r["holders"] else None,
                    top10=dec(r["top10_share"]),
                    dev_share=dec(r["dev_share"]),
                    participants=int(r["participants"]) if r["participants"] else None,
                    snipers=int(r["snipers"]) if r["snipers"] else None,
                    kol=int(r["kol_count"]) if r["kol_count"] else None,
                    censored=r["exposure_censored"] == "t",
                )
            )
    rate = _sol_usd_series(raw)
    fallback = Decimal(str(statistics.median([float(v) for v in rate.values()]))) if rate else None
    series: dict[str, list[dict]] = {}
    for r in raw:
        if r["mcap_usd"] is None or r["observed_at"] is None:
            continue
        key = r["observed_at"].replace(second=0, microsecond=0)
        sol_usd = rate.get(key) or fallback
        if not sol_usd:
            continue
        r["sol_usd"] = sol_usd
        r["mcap_sol"] = r["mcap_usd"] / sol_usd
        r["dt_s"] = (r["observed_at"] - r["migrated_at"]).total_seconds()
        series.setdefault(r["mint"], []).append(r)
    for m in series:
        series[m].sort(key=lambda x: x["observed_at"])
    return series


def entry_point(obs: list[dict]) -> dict | None:
    """Primeira leitura do board em ou depois de migrated_at - o instante da decisao."""
    for o in obs:
        if o["dt_s"] >= 0 and o["mcap_sol"] and o["mcap_sol"] > 0:
            return o
    return None


def value_at(obs: list[dict], t0: datetime, seconds: int, tol: int = 90) -> dict | None:
    """Leitura mais proxima de t0+seconds, aceite se dentro de `tol` s. Nunca extrapola.

    A leitura tem de ser ESTRITAMENTE POSTERIOR a entrada (`observed_at > t0`): sem isto
    um mint com uma unica leitura devolvia a propria entrada como "retorno a +1 min" e
    produzia um zero artificial (must-fix 3 da Astra, 22/09).
    """
    target = t0 + timedelta(seconds=seconds)
    best, bestgap = None, None
    for o in obs:
        if o["observed_at"] <= t0:
            continue
        gap = abs((o["observed_at"] - target).total_seconds())
        if bestgap is None or gap < bestgap:
            best, bestgap = o, gap
    if best is None or bestgap is None or bestgap > tol:
        return None
    return best


def window(obs: list[dict], t0: datetime, seconds: int) -> list[dict]:
    end = t0 + timedelta(seconds=seconds)
    return [o for o in obs if t0 <= o["observed_at"] <= end]


def load_pregrad(path: str = "pregrad.csv") -> dict[str, dict]:
    out: dict[str, dict] = {}
    p = HERE / path
    if not p.exists():
        return out
    with open(p, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[r["mint"]] = dict(
                board=r["board"],
                observed_at=ts(r["observed_at"]),
                mcap_usd=dec(r["market_cap_usd"]),
                progress_pct=dec(r["progress_pct"]),
                volume_sol=dec(r["volume_sol"]),
                volume_5m_sol=dec(r["volume_5m_sol"]),
                volume_1h_sol=dec(r["volume_1h_sol"]),
                txs=int(r["txs"]) if r["txs"] else None,
                buys=int(r["buys"]) if r["buys"] else None,
                sells=int(r["sells"]) if r["sells"] else None,
                holders=int(r["holders"]) if r["holders"] else None,
                top10=dec(r["top10_share"]),
                dev_share=dec(r["dev_share"]),
                participants=int(r["participants"]) if r["participants"] else None,
                snipers=int(r["snipers"]) if r["snipers"] else None,
                kol=int(r["kol_count"]) if r["kol_count"] else None,
                age_s=int(r["age_s"]) if r["age_s"] else None,
                has_social=r["has_social"] == "t",
            )
    return out


if __name__ == "__main__":
    tokens = load_tokens()
    series = load_board(tokens)
    n_entry = sum(1 for m in series if entry_point(series[m]))
    spans = sorted(s[-1]["dt_s"] for s in series.values())
    print("tokens migrados 7d:", len(tokens))
    print("com serie do board:", len(series), "| com ponto de entrada:", n_entry)
    print(
        "span (s) p10/p50/p90:",
        spans[len(spans) // 10],
        spans[len(spans) // 2],
        spans[len(spans) * 9 // 10],
    )
    obs_total = sum(len(s) for s in series.values())
    print("observacoes:", obs_total)
