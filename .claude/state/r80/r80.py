# R80 — H-020: identidade social reciclada. Funções puras (sem IO fora de load_*).
from __future__ import annotations

import bisect
import csv
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "infra" / "scripts"))
from meme_daily_ficha_classify import LossClassInputs, classify_loss  # noqa: E402

LOOKBACK = timedelta(hours=24)

_HOST = re.compile(r"^(?:https?://)?(?:www\.|mobile\.)?(?:twitter\.com|x\.com)(?=/|$)", re.IGNORECASE)
_STATUS = re.compile(r"^([A-Za-z0-9_]{1,15})/status(?:es)?/(\d{1,19})(?:/|$)", re.IGNORECASE)
_COMMUNITY = re.compile(r"^i/communities/(\d+)(?:/|$)", re.IGNORECASE)
_PROFILE = re.compile(r"^([A-Za-z0-9_]{1,15})$")
_RESERVED = frozenset({"i", "home", "explore", "search", "notifications", "messages", "settings", "compose", "hashtag"})


def normalize_twitter(url: str | None) -> tuple[str, str] | None:
    """(chave, tipo). Perfil: handle minúsculo; post: o id do status (o handle na URL é irrelevante,
    o id é global); comunidade: o id; outro: o texto minúsculo sem esquema/www/fragmento/barra final,
    **com** a query (uma busca `?q=$DOG` não é a mesma coisa que `?q=$CAT`)."""
    if url is None or not url.strip():
        return None
    raw = url.strip()
    host = _HOST.match(raw)
    if host:
        rest = raw[host.end():]
        path, _, _query = rest.partition("?")
        path = path.split("#", 1)[0].strip("/")
        m = _COMMUNITY.match(path)
        if m:
            return f"community:{m.group(1)}", "community"
        m = _STATUS.match(path)
        if m and int(m.group(2)).bit_length() <= 63:
            return f"post:{int(m.group(2))}", "post"
        m = _PROFILE.match(path)
        if m and m.group(1).lower() not in _RESERVED:
            return f"profile:{m.group(1).lower()}", "profile"
    low = re.sub(r"^(?:https?://)?(?:www\.|mobile\.)?", "", raw.lower()).split("#", 1)[0]
    base, sep, query = low.partition("?")
    return f"other:{base.rstrip('/')}{sep}{query}", "other"


def ts(s: str | None) -> datetime | None:
    if s is None or s == "":
        return None
    d = datetime.fromisoformat(s.replace(" ", "T") if "T" not in s else s)
    if d.tzinfo is None:
        raise ValueError(f"timestamp ingénuo: {s}")
    return d.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class _Tok:
    created: datetime
    observed: datetime | None
    key: str | None
    kind: str | None


class TokenIndex:
    """Universo de moedas: reuso do link nas 24 h anteriores e cobertura (legível / criadas)."""

    def __init__(self, rows: list[dict]) -> None:
        self.tok: dict[str, _Tok] = {}
        by_key: dict[str, list[tuple[datetime, str, datetime | None]]] = defaultdict(list)
        created: list[datetime] = []
        observed_at: list[float] = []
        for r in rows:
            c = r["created_at"]
            if c is None:
                continue
            if r["mint"] in self.tok:
                raise ValueError(f"mint duplicado no universo: {r['mint']}")
            norm = normalize_twitter(r["twitter"])
            key, kind = (None, None) if norm is None else norm
            t = _Tok(c, r["social_observed_at"], key, kind)
            self.tok[r["mint"]] = t
            if key is not None:
                by_key[key].append((c, r["mint"], t.observed))
            created.append(c)
            observed_at.append(np.inf if t.observed is None else t.observed.timestamp())
        self.by_key = {k: sorted(v) for k, v in by_key.items()}
        self._keys_created = {k: [e[0] for e in v] for k, v in self.by_key.items()}
        order = np.argsort(np.array([c.timestamp() for c in created]))
        self._c = np.array([created[i].timestamp() for i in order])
        self._obs = np.array(observed_at)[order]

    def has_twitter(self, mint: str) -> bool | None:
        t = self.tok.get(mint)
        if t is None or t.observed is None:
            return None
        return t.key is not None

    def kind(self, mint: str) -> str | None:
        t = self.tok.get(mint)
        return None if t is None else t.kind

    def key(self, mint: str) -> str | None:
        t = self.tok.get(mint)
        return None if t is None else t.key

    def reuse(self, mint: str, decision: datetime, *, known_only: bool = False) -> int | None:
        """Outras moedas com o mesmo link e created_at em [decisão − 24 h, decisão) — estrito.
        `known_only`: também exige a identidade observada antes da decisão (a própria e as outras)."""
        t = self.tok.get(mint)
        if t is not None and t.created >= decision:
            raise ValueError(f"{mint}: moeda criada em/depois da decisão ({t.created} >= {decision})")
        if t is None or t.observed is None:
            return None
        if known_only and t.observed >= decision:
            return None
        if t.key is None:
            return 0
        entries = self.by_key[t.key]
        cs = self._keys_created[t.key]
        lo = bisect.bisect_left(cs, decision - LOOKBACK)
        hi = bisect.bisect_left(cs, decision)  # created_at < decisão
        n = 0
        for c, m, obs in entries[lo:hi]:
            if m == mint:
                continue
            if known_only and (obs is None or obs >= decision):
                continue
            n += 1
        return n

    def matched(self, mint: str, decision: datetime) -> list[tuple[datetime, str, datetime | None]]:
        t = self.tok.get(mint)
        if t is None or t.key is None:
            return []
        cs = self._keys_created[t.key]
        lo = bisect.bisect_left(cs, decision - LOOKBACK)
        hi = bisect.bisect_left(cs, decision)
        return [e for e in self.by_key[t.key][lo:hi] if e[1] != mint]

    def coverage(self, decision: datetime, *, known_only: bool = False) -> float | None:
        """Fração das moedas criadas em [T − 24 h, T) com identidade observada (ever, ou antes de T)."""
        a = np.searchsorted(self._c, (decision - LOOKBACK).timestamp(), side="left")
        b = np.searchsorted(self._c, decision.timestamp(), side="left")
        n = int(b - a)
        if n == 0:
            return None
        obs = self._obs[a:b]
        k = np.isfinite(obs) if not known_only else obs < decision.timestamp()
        return float(k.sum()) / n


def first_per_mint(rows: list[dict]) -> list[dict]:
    """1.ª decisão por mint: menor decided_at; empate → real; depois entry_at."""
    best: dict[str, dict] = {}
    for r in rows:
        k = (ts(r["decided_at"]), 0 if r["lane"] == "real" else 1, ts(r["entry_at"]) or ts(r["decided_at"]))
        cur = best.get(r["mint"])
        if cur is None or k < cur[0]:
            best[r["mint"]] = (k, r)
    return [v[1] for v in best.values()]


def golpe_ficha(*, pnl: Decimal, peak_le_cost: bool | None, exit_reason: str | None, sellers: int | None) -> bool:
    """A classe da ficha (T4.92), com a mesma ordem: comprou_no_topo é checada antes."""
    cost = Decimal(1)
    hw = None if peak_le_cost is None else (cost if peak_le_cost else cost + 1)
    cls = classify_loss(LossClassInputs(pnl_sol=pnl, cost_sol=cost, high_water_sol=hw, exit_reason=exit_reason,
                                        distinct_sellers_one_slot=sellers, since_prior_exit=None,
                                        round_trip_cost_sol=None))
    return cls == "golpe_do_criador"


def golpe_raw(*, pnl: Decimal, exit_reason: str | None, sellers: int | None) -> bool | None:
    """O texto da H-020: perda com saída creator_dump, ou perda com ≥ 10 vendedores num slot.
    Fita da posse desconhecida (`sellers` None) sem creator_dump → None: não comprova ausência."""
    if pnl >= 0:
        return False
    if exit_reason == "creator_dump" or (sellers is not None and sellers >= 10):
        return True
    return None if sellers is None else False


def peak_le_cost(r: dict) -> bool | None:
    """Real: high_water_sol ≤ initial_risk_sol; papel: high_water_x ≤ 1 (R79)."""
    if r["lane"] == "real":
        if not r["hw_sol"] or not r["cost_sol"]:
            return None
        return Decimal(r["hw_sol"]) <= Decimal(r["cost_sol"])
    if not r["hw_x"]:
        return None
    return Decimal(r["hw_x"]) <= 1


def load_tokens(path: Path = HERE / "cache" / "tok.csv") -> list[dict]:
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.append({"mint": r["mint"], "created_at": ts(r["created_at"]), "twitter": r["twitter"] or None,
                        "social_observed_at": ts(r["social_observed_at"])})
    return out


def load_pop(path: Path = HERE / "cache" / "pop.csv") -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def resolved(r: dict) -> bool:
    return (r["status"] == "closed" and r["pnl_sol"] != "" and r["size_sol"] != ""
            and Decimal(r["size_sol"]) > 0 and r["oq"] != "indeterminate")


def r_of(r: dict) -> float:
    return float(Decimal(r["pnl_sol"]) / Decimal(r["size_sol"]))
