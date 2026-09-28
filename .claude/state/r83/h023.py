"""R83 / H-023 — população, reconstrução causal de `distance_from_24h_high/_low` e tercis.

Puro e offline: lê os CSV exportados da VPS (`cache/feat.csv` cego, `cache/out.csv` com os
desfechos) e devolve `list[dict]` no formato do moinho (`infra.research.protocol`).

A feature não está no envelope de nenhum sinal (`env_dh` vazio em 100 %), então é
**reconstruída** das velas `candles_1m` com a fórmula de produção
(`packages/indicators/hunter_indicators/features/price.py:106`, `DistanceFromExtreme` v1):
as 1 440 velas 1m `is_final` **contíguas** cuja abertura está em `[obs − 1440 min, obs − 1 min]`
(fecham em ou antes de `obs` = `observation_ts` do envelope = fecho da barra de decisão);
`d_high = (close_última − max(high)) / max(high)`, `d_low = (close_última − min(low)) / min(low)`.
Janela incompleta = ausente (nunca zero). O teste `test_r83.py` prova que o valor é o mesmo da
classe de produção e que não muda quando uma vela posterior a `obs` (ou não final) muda.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path

from infra.research.guards import Instants, check_observable
from infra.research.stats import terciles

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
WINDOW = 1440
MIN = timedelta(minutes=1)

CONT = ("momentum", "breakout", "volume_anomaly", "session_orb")
"""Continuação (compra força/rompimento) — a família com sinal previsto (+)."""
MR = ("mean_reversion", "mean_reversion_h1", "mean_reversion_m5")
"""Reversão — reportada à parte, sem sinal previsto."""
OTHER = ("trendline_breakout", "trendline_bounce", "sweep_reclaim")
"""Estrutura (reta/pivô) — nem continuação pura nem reversão: só descritivo."""

GRID = (Fraction(1, 5), Fraction(1, 4), Fraction(3, 10), Fraction(1, 3), Fraction(2, 5),
        Fraction(9, 20), Fraction(1, 2))
"""Cortes vizinhos do patamar: extremo q de cima contra extremo q de baixo (q = 1/3 é o tercil)."""


def family(strategy: str) -> str:
    if strategy in CONT:
        return "continuacao"
    if strategy in MR:
        return "reversao"
    if strategy in OTHER:
        return "outras"
    raise ValueError(f"estratégia sem família declarada: {strategy!r}")


def ts(text: str | None) -> datetime | None:
    """`timestamptz` do Postgres → datetime UTC aware; vazio continua ausente."""
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


def distance(close_last: Decimal, extreme: Decimal) -> Decimal | None:
    """`(close − extremo) / extremo`, a aritmética de `DistanceFromExtreme.compute`."""
    if extreme <= 0:
        return None
    with localcontext() as ctx:
        ctx.prec = 28
        return (close_last - extreme) / extreme


def window_ok(n: int, first_open: datetime | None, last_open: datetime | None, obs: datetime) -> str | None:
    """Motivo da ausência, ou None se a janela de 1 440 min fechados em `obs` está inteira."""
    if first_open is None or last_open is None or n == 0:
        return "sem_velas"
    if last_open != obs - MIN:
        return "ultima_vela_ausente"
    if n != WINDOW or first_open != obs - WINDOW * MIN:
        return "janela_incompleta"
    return None


def _ratio(num: Decimal | None, den: Decimal | None) -> float | None:
    if num is None or den is None or den <= 0:
        return None
    return float(num / den - 1)


def feature_row(raw: Mapping[str, str]) -> dict[str, object]:
    """Uma linha do export cego → a linha do estudo (sem desfecho)."""
    obs = ts(raw["obs"])
    emitted = ts(raw["emitted_at"])
    assert obs is not None and emitted is not None
    first, last = ts(raw["first_open"]), ts(raw["last_open"])
    n = int(raw["n"] or 0)
    close_last = dec(raw["close_last"])
    why = window_ok(n, first, last, obs)
    dh = dl = None
    if why is None and close_last is not None:
        hi, lo = dec(raw["hi24"]), dec(raw["lo24"])
        assert hi is not None and lo is not None
        vh, vl = distance(close_last, hi), distance(close_last, lo)
        dh = None if vh is None else float(vh)
        dl = None if vl is None else float(vl)
    atr = dec(raw["env_atr_pct"])
    ret15 = _ratio(close_last, dec(raw["close_m15"]))
    prospective = raw["cohort"] == "prospective"
    max_recv = ts(raw["max_recv"])
    return {
        "signal_id": raw["signal_id"],
        "strategy": raw["strategy"],
        "version": raw["version"],
        "sv": f"{raw['strategy']}/{raw['version']}",
        "family": family(raw["strategy"]),
        "cohort": raw["cohort"],
        "prospective": prospective,
        "market": raw["market_id"],
        "symbol": raw["symbol"],
        "market_type": raw["market_type"],
        "obs": obs,
        "t": emitted,
        "day": obs.date().isoformat(),
        "has_r": raw["has_r"] == "t",
        "r_net_reason": raw["r_net_reason"] or None,
        "window_reason": why,
        "d_high": dh,
        "d_low": dl,
        "ret15": ret15,
        "ret60": _ratio(close_last, dec(raw["close_m60"])),
        "ret240": _ratio(close_last, dec(raw["close_m240"])),
        "atr_pct": None if atr is None else float(atr),
        "atr_tf": raw["env_atr_tf"] or None,
        "mom15": None if ret15 is None or atr is None or atr <= 0 or raw["env_atr_tf"] != "15m"
        else ret15 / float(atr),
        "env_ret15": None if not raw["env_ret15"] else float(raw["env_ret15"]),
        "env_z15": None if not raw["env_z15"] else float(raw["env_z15"]),
        "env_rvol": None if not raw["env_rvol"] else float(raw["env_rvol"]),
        "env_dh": raw["env_dh"] or None,
        # instantes para a guarda do moinho (check_observable): a janela termina em `obs`;
        # na coorte prospectiva, a última chegada das velas usadas tem de ser <= emissão;
        # no replay, o contexto é cortado em source_bar_close por construção e a chegada
        # das velas (backfill) não é o que o replay sabia — declarado, não verificado.
        "as_of": obs,
        "computed_at": (max_recv if prospective else obs) or obs,
    }


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def population(rows: Iterable[dict[str, object]]) -> tuple[list[dict[str, object]], Counter[str]]:
    """Só perpétuo; uma decisão por (versão, mercado, obs) — prospectiva antes de replay."""
    cnt: Counter[str] = Counter()
    best: dict[tuple[object, ...], dict[str, object]] = {}
    for r in rows:
        if r["market_type"] != "perpetual":
            cnt["fora_spot"] += 1
            continue
        key = (r["sv"], r["market"], r["obs"])
        rank = (0 if r["prospective"] else 1, str(r["cohort"]), str(r["signal_id"]))
        cur = best.get(key)
        if cur is None:
            best[key] = r
            continue
        cnt["fora_duplicada"] += 1
        cur_rank = (0 if cur["prospective"] else 1, str(cur["cohort"]), str(cur["signal_id"]))
        if rank < cur_rank:
            best[key] = r
    out = sorted(best.values(), key=lambda r: (r["obs"], str(r["signal_id"])))  # type: ignore[arg-type]
    cnt["dentro"] = len(out)
    return out, cnt


def cut_labels(values: Sequence[float], q: Fraction) -> tuple[float, float]:
    """(corte de baixo, corte de cima) do extremo q, na convenção de `terciles` do moinho."""
    xs = sorted(values)
    n = len(xs)
    lo = xs[int(n * q)]
    hi = xs[int(n * (1 - q))] if q != Fraction(1, 2) else xs[n // 2]
    return float(lo), float(hi)


def assign_extremes(rows: Sequence[dict[str, object]], var: str, q: Fraction, group: str = "strategy",
                    ) -> list[str | None]:
    """'baixo' (≤ corte_q), 'alto' (> corte_{1−q}) ou None, com cortes **dentro** de `group`.

    Empates ficam juntos (a comparação é por valor). Para q = 1/3 os cortes são os de
    `infra.research.stats.terciles` (xs[n//3], xs[2n//3]).
    """
    by: dict[object, list[float]] = defaultdict(list)
    for r in rows:
        v = r[var]
        if v is not None:
            by[r[group]].append(float(v))  # type: ignore[arg-type]
    cuts: dict[object, tuple[float, float]] = {}
    for g, xs in by.items():
        if len(xs) < 6:
            continue
        if q == Fraction(1, 3):
            t = terciles(xs)
            assert t is not None
            cuts[g] = t
        else:
            cuts[g] = cut_labels(xs, q)
    out: list[str | None] = []
    for r in rows:
        v, c = r[var], cuts.get(r[group])
        if v is None or c is None:
            out.append(None)
        elif float(v) <= c[0]:  # type: ignore[arg-type]
            out.append("baixo")
        elif float(v) > c[1]:  # type: ignore[arg-type]
            out.append("alto")
        else:
            out.append(None if q != Fraction(1, 3) else "meio")
    return out


def load_features() -> tuple[list[dict[str, object]], Counter[str]]:
    rows = [feature_row(r) for r in read_csv(CACHE / "feat.csv")]
    return population(rows)


def guarded(rows: Iterable[dict[str, object]]) -> tuple[list[dict[str, object]], int]:
    """A guarda do moinho (`check_observable`) sobre cada linha, antes de qualquer corte."""
    kept, refused = [], 0
    for r in rows:
        why = check_observable(Instants(r["as_of"], r["computed_at"]), r["t"], str(r["signal_id"]))  # type: ignore[arg-type]
        if why is None:
            kept.append(r)
        else:
            refused += 1
    return kept, refused


def fila_label(*, n: int, rho_max: float, d: float, lo: float, hi: float, p: float, p_holm: float,
               level_alto: float, shape: str, mre: float = 0.05) -> tuple[str, list[str]]:
    """O rótulo da H-023 pela ordem congelada em notes-R83.md §2.7 (com a errata do R76)."""
    notes: list[str] = []
    if rho_max >= 0.8 or n < 150:
        return "LIMITE DE DADO/MEDIDA", [f"|ρ| máx {rho_max:.3f}, n {n}"]
    if lo < -0.01:
        notes.append(f"cláusula literal 'IC inf < −0,01' aciona (IC inf {lo:+.4f}) — pela errata sozinha não refuta")
    if hi < 0.01:
        return "REFUTA", notes + [f"IC sup {hi:+.4f} < +0,01" + (" (efeito oposto sustentado)" if hi < -0.01 else "")]
    checks = [(d >= mre, f"D {d:+.4f} < {mre:+.2f}"), (lo > 0, f"IC inf {lo:+.4f} ≤ 0"), (p < 0.05, f"p {p:.4f}"),
              (p_holm <= 0.05, f"Holm {p_holm:.4f}"), (level_alto > 0, f"tercil alto {level_alto:+.4f} ≤ 0 em nível"),
              (shape == "planalto", f"curva {shape}")]
    failed = [why for ok, why in checks if not ok]
    if not failed:
        return "CONFIRMA", notes
    return "NÃO CONFIRMA", notes + failed
