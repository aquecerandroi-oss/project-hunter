"""R73 / H-010 — `maior_comprador_pct` reconstruído da fita, com guarda anti-antecipação.

Método herdado do R62 (`.claude/state/r62/analyze.py`) e do R64 (`.claude/state/r64/load.py`):
a fita `meme_trades` é a única fonte; o SOL real da curva é a soma com sinal de
`sol_lamports` desde o nascimento (compra soma, venda subtrai), exatamente como aqueles
estudos atualizavam as reservas virtuais.

A variável (congelada no bloco H-010 da fila):

    maior_comprador_pct = max_carteira( compras − vendas, em lamports ) / SOL real da curva

ambos medidos **no instante da decisão** e **só com o que estava na nossa fita nesse
instante**: `block_time <= decisão` **e** `received_at <= decisão` (exigência da T4.80 —
uma troca que aconteceu na cadeia antes da decisão mas chegou ao nosso coletor depois
**não** era informação nossa).

Dinheiro em inteiros (lamports) e `Decimal` nas fronteiras; a razão sai em float porque é
estatística, não dinheiro.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUR = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
BRT = timezone(timedelta(hours=-3))


def ts(s: str) -> datetime:
    """Timestamp do Postgres (`+00`) para `datetime` UTC aware. Ingénuo é recusado."""
    s = s.strip()
    if not s:
        raise ValueError("timestamp vazio")
    s = s.replace(" ", "T")
    if s.endswith("+00"):
        s += ":00"
    d = datetime.fromisoformat(s)
    if d.tzinfo is None or d.tzinfo.utcoffset(d) is None:
        raise ValueError(f"timestamp ingénuo: {s!r} — o tempo desta análise é UTC aware")
    return d


def brt(d: datetime, fmt: str = "%H:%M:%S") -> str:
    return d.astimezone(BRT).strftime(fmt)


@dataclass(frozen=True)
class Trade:
    """Uma linha da fita. `sol` em lamports; `side` em {'buy', 'sell'}."""

    block_time: datetime
    received_at: datetime
    slot: int
    event_index: int
    trader: str
    side: str
    sol: int
    tok: int = 0
    """Tokens da troca em unidades inteiras (já com as casas decimais aplicadas)."""

    @property
    def signed(self) -> int:
        """Fluxo de SOL para a curva: compra entra, venda sai."""
        return self.sol if self.side == "buy" else -self.sol

    @property
    def signed_tok(self) -> int:
        """Fluxo de tokens para a carteira: compra recebe, venda devolve."""
        return self.tok if self.side == "buy" else -self.tok


@dataclass(frozen=True)
class Concentration:
    """O que a fita diz no instante da decisão, e o que a guarda cortou."""

    pct: float | None
    """`maior_comprador_pct` — variável principal, pré-registada: líquido em SOL.
    `None` quando a curva reconstruída não é positiva."""

    pct_bruto: float | None
    """Sensibilidade: maior soma de **compras brutas** / curva (a letra do bloco H-010)."""

    pct_estoque: float | None
    """Sensibilidade (contraexemplo da Astra): maior **estoque de tokens** de uma carteira
    sobre os tokens que saíram da curva. Mede capacidade de despejo, não fluxo de SOL."""

    top_wallet: str | None
    top_net_lamports: int
    top_gross_lamports: int
    top_stock_tok: int
    curve_tok_out: int
    curve_lamports: int
    n_trades: int
    n_wallets: int
    blocked_by_guard: int
    """Trocas com `block_time <= decisão` mas `received_at > decisão` — o que a cadeia
    já sabia e nós ainda não. É a conta que a T4.80 exige publicar."""

    blocked_lamports: int
    last_block_time: datetime | None
    last_received_at: datetime | None

    @property
    def curve_sol(self) -> Decimal:
        return Decimal(self.curve_lamports) / Decimal(10**9)

    @property
    def top_net_sol(self) -> Decimal:
        return Decimal(self.top_net_lamports) / Decimal(10**9)


def concentration(
    tape: list[Trade],
    decision: datetime,
    *,
    guard: bool = True,
    exclude: frozenset[str] = frozenset({OUR}),
) -> Concentration:
    """`maior_comprador_pct` no instante `decision`.

    `guard=True` (o modo de produção do estudo) exige **as duas** condições: a troca
    aconteceu antes da decisão *e* já tinha chegado ao nosso coletor. `guard=False`
    existe só para medir quanto a guarda corta e para a aferição de cobertura contra a
    foto da curva (que reflete o estado da cadeia, não o nosso conhecimento).
    """
    if decision.tzinfo is None or decision.tzinfo.utcoffset(decision) is None:
        raise ValueError("instante de decisão ingénuo — comparar ingénuo com aware não guarda nada")
    net: dict[str, int] = defaultdict(int)
    gross: dict[str, int] = defaultdict(int)
    stock: dict[str, int] = defaultdict(int)
    curve = 0
    curve_tok = 0
    used = 0
    blocked = 0
    blocked_lamports = 0
    last_bt: datetime | None = None
    last_rcv: datetime | None = None
    for t in tape:
        if t.block_time > decision:
            continue
        if guard and t.received_at > decision:
            blocked += 1
            blocked_lamports += abs(t.sol)
            continue
        used += 1
        curve += t.signed
        curve_tok += t.signed_tok
        if t.trader not in exclude:
            net[t.trader] += t.signed
            stock[t.trader] += t.signed_tok
            if t.side == "buy":
                gross[t.trader] += t.sol
        if last_bt is None or t.block_time > last_bt:
            last_bt = t.block_time
        if last_rcv is None or t.received_at > last_rcv:
            last_rcv = t.received_at
    top_wallet, top_net = _argmax(net)
    _, top_gross = _argmax(gross)
    _, top_stock = _argmax(stock)
    return Concentration(
        pct=(top_net / curve) if curve > 0 else None,
        pct_bruto=(top_gross / curve) if curve > 0 else None,
        pct_estoque=(top_stock / curve_tok) if curve_tok > 0 else None,
        top_wallet=top_wallet,
        top_net_lamports=top_net,
        top_gross_lamports=top_gross,
        top_stock_tok=top_stock,
        curve_tok_out=curve_tok,
        curve_lamports=curve,
        n_trades=used,
        n_wallets=len(net),
        blocked_by_guard=blocked,
        blocked_lamports=blocked_lamports,
        last_block_time=last_bt,
        last_received_at=last_rcv,
    )


def _argmax(d: dict[str, int]) -> tuple[str | None, int]:
    """Maior valor do mapa; negativo (carteira já sem posição) não é um 'maior comprador'."""
    if not d:
        return None, 0
    who, value = max(d.items(), key=lambda kv: kv[1])
    return (who, value) if value > 0 else (None, 0)


def curve_sol_at(
    tape: list[Trade], instant: datetime, *, known_by: datetime | None = None
) -> tuple[int, int]:
    """SOL real reconstruído (lamports) em `instant` e em `instant + 1 s`.

    `known_by` liga a guarda de chegada: só entram trocas com `received_at <= known_by`.
    Com ela a aferição mede **o que a nossa fita sabia**; sem ela mede o estado da cadeia.
    `block_time` tem resolução de 1 s, por isso a aferição usa uma banda e não um ponto
    (a foto pode cair no meio de um segundo cheio de trocas).
    """

    def ok(t: Trade) -> bool:
        return known_by is None or t.received_at <= known_by

    lo = sum(t.signed for t in tape if t.block_time <= instant and ok(t))
    hi = lo + sum(
        t.signed
        for t in tape
        if instant < t.block_time <= instant + timedelta(seconds=1) and ok(t)
    )
    return lo, hi


def load_tape(path: Path | None = None) -> dict[str, list[Trade]]:
    """Fita exportada da VPS, agrupada por mint e ordenada por (slot, event_index)."""
    path = path or HERE / "tape.csv"
    by_mint: dict[str, list[Trade]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            by_mint[r["mint"]].append(
                Trade(
                    block_time=ts(r["block_time"]),
                    received_at=ts(r["received_at"]),
                    slot=int(r["slot"]),
                    event_index=int(r["event_index"]),
                    trader=r["trader"],
                    side=r["side"],
                    sol=int(r["sol_lamports"]),
                    tok=int(r["token_raw"] or 0),
                )
            )
    for m in by_mint:
        by_mint[m].sort(key=lambda t: (t.slot, t.event_index))
    return dict(by_mint)


def load_population(path: Path | None = None) -> list[dict[str, object]]:
    """Posições reais e apostas de papel exportadas, com os campos já tipados."""
    path = path or HERE / "pop.csv"
    rows: list[dict[str, object]] = []
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            size = Decimal(r["size_sol"]) if r["size_sol"] else None
            pnl = Decimal(r["pnl_sol"]) if r["pnl_sol"] else None
            rows.append(
                {
                    "lane": r["lane"],
                    "bet_id": r["bet_id"],
                    "mint": r["mint"],
                    "symbol": r["symbol"] or r["mint"][:6],
                    "creator": r["creator"],
                    "rule_set": r["rule_set"],
                    "rs_kind": r["rs_kind"],
                    "decided_at": ts(r["decided_at"]),
                    "quote_observed_at": ts(r["quote_observed_at"]) if r["quote_observed_at"] else None,
                    "quote_real_sol": Decimal(r["quote_real_sol"]) if r["quote_real_sol"] else None,
                    "quote_source": r["quote_source"],
                    "token_created_at": ts(r["token_created_at"]) if r["token_created_at"] else None,
                    "entry_at": ts(r["entry_at"]) if r["entry_at"] else None,
                    "exit_at": ts(r["exit_at"]) if r["exit_at"] else None,
                    "exit_reason": r["exit_reason"],
                    "size_sol": size,
                    "pnl_sol": pnl,
                    "r_multiple": Decimal(r["r_multiple"]) if r["r_multiple"] else None,
                    "ret": float(pnl / size) if (pnl is not None and size) else None,
                    "dia": r["decided_at"][:10],
                    "hora": r["decided_at"][:13],
                }
            )
    return rows


# --------------------------------------------------------------------------- cobertura

COVERAGE_TOL = Decimal("0.02")
"""Banda relativa da aferição fita × foto da curva. 2 % de uma curva de ~30 SOL é
~0,6 SOL — folga para arredondamento de reservas e para a resolução de 1 s do
`block_time`, apertada o bastante para apanhar fita que começou depois do nascimento."""


def tape_matches_curve(
    tape: list[Trade],
    quote_observed_at: datetime,
    quote_real_sol: Decimal | None,
    *,
    known_by: datetime | None = None,
) -> tuple[bool, float]:
    """A fita desde o nascimento reproduz a foto da curva? Devolve (bate, erro relativo).

    Definição operacional de *"temos fita desde o nascimento"*: se faltam trocas no
    início, o SOL reconstruído fica abaixo da foto e o erro dispara.

    **Necessária, não suficiente** (contraexemplo da Astra na revisão prévia): omissões
    que se compensam — falta uma compra de 10 e uma venda de 10 — deixam a reserva certa
    e os saldos por carteira errados. Por isso a elegibilidade exige também a âncora de
    nascimento (`tape_starts_at_birth`), e a ressalva fica escrita no relatório.

    `known_by` (= instante da decisão) torna a elegibilidade **decidível na decisão**:
    sem ele uma troca que chegou atrasada podia fazer uma decisão entrar na população
    por informação que nós não tínhamos.
    """
    if quote_real_sol is None or quote_real_sol <= 0:
        return False, float("inf")
    lo, hi = curve_sol_at(tape, quote_observed_at, known_by=known_by)
    q = int((quote_real_sol * Decimal(10**9)).to_integral_value())
    lo_b, hi_b = min(lo, hi), max(lo, hi)
    if lo_b <= q <= hi_b:
        return True, 0.0
    dist = min(abs(q - lo_b), abs(q - hi_b))
    err = dist / q
    return err <= float(COVERAGE_TOL), err


BIRTH_SLACK = timedelta(seconds=5)
"""Folga da âncora de nascimento: a primeira troca da fita tem de estar a ≤ 5 s do
`created_at` do token. A compra do criador costuma ser a própria transação de criação."""


def tape_starts_at_birth(
    tape: list[Trade], token_created_at: datetime | None
) -> tuple[bool, float | None]:
    """A fita começa no nascimento? Devolve (sim, atraso em segundos da 1.ª troca).

    Segunda condição, independente da reconciliação de reservas: apanha o caso em que o
    coletor entrou no mint a meio da vida dele e as omissões iniciais se compensaram.
    """
    if token_created_at is None or not tape:
        return False, None
    first = min(t.block_time for t in tape)
    delay = (first - token_created_at).total_seconds()
    return delay <= BIRTH_SLACK.total_seconds(), delay
