"""The frozen selection rule of the paper copy-trade pilot (decision
2026-10-09) and the pure functions that apply it to ``/pnl-leaderboard`` rows.

No network, no clock, no database: ``copy_select_leaders.py`` fetches, this
module decides. The rule text below is pre-declared, hashed (sha256) and
printed by the tool; it was frozen before any result of the pilot existed.
The leaderboard is not point-in-time (KB-0185): the list only says whom to
observe from now on, never how much the leaders "would have" made.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from copy_leaders_parse import (
    BoardRow,
    ParsedBoard,
    RuleError,
)
from copy_leaders_parse import (
    BoardShapeError as BoardShapeError,
)
from copy_leaders_parse import (
    parse_board as parse_board,
)

RULE_VERSION = "copy-leaders-rule/1"
STRATUM_RULE = "regra"
STRATUM_EVERTON = "escolha_everton"

PERIODS_LONGEST_FIRST = ("monthly", "weekly", "daily")
SORTS = ("combined", "realized")
PERIOD_DAYS = {"daily": 1, "weekly": 7, "monthly": 30}

TOP_N = 20
MAX_INCLUDES = 4
MIN_PERIODS = 2
MIN_POSITIONS = 10
MIN_REALIZED_SHARE = Decimal("0.5")
MISSING_POSITION = 101
BOARD_ROWS = 100

RULE_TEXT = f"""\
REGRA {RULE_VERSION} (congelada antes de qualquer resultado do piloto)
1. Universo: as 6 visões do /pnl-leaderboard (daily, weekly e monthly x combined e realized), \
100 linhas cada. Endereço que não é Solana (base58 de 32 a 44 caracteres) sai.
2. Persistência: aparece em pelo menos {MIN_PERIODS} PERÍODOS distintos (combined e realized do \
mesmo período contam como um). As janelas se sobrepõem: não são sucessos independentes.
3. Linha de referência: a do período mais longo em que a carteira aparece (monthly, weekly, \
daily); nele, a visão combined se existir, senão a realized. Os números dos itens 5 a 7 vêm dela.
4. Realizado positivo (realizedPnlSol > 0) em TODAS as linhas da carteira.
5. Não é marcação: buySpendSol > 0 e realizado / (realizado + max(não realizado, 0)) >= \
{str(MIN_REALIZED_SHARE).replace(".", ",")}.
6. Saldo positivo: realizado + não realizado > 0 na linha de referência.
7. Massa mínima: positionsCount >= {MIN_POSITIONS} na linha de referência. A razão \
posições por dia é só descritiva (não há detecção verificada de robô nos campos do quadro).
8. Ordem: média das posições (1 a 100, na lista devolvida) da carteira nos três quadros \
realized (daily, weekly, monthly); ausente de um quadro = {MISSING_POSITION}; menor primeiro; \
empate por endereço crescente. Ficam as {TOP_N} primeiras; se passarem menos, ficam menos \
(a regra não se afrouxa sozinha).
9. isVerified e seguidores são descritivos: não alteram elegibilidade nem ordem. Seguidor \
não lido é desconhecido, nunca 0.
10. --include (até {MAX_INCLUDES}): entra sem os filtros 2 a 8, no estrato {STRATUM_EVERTON}. Se a \
regra também a escolheria (top {TOP_N}), fica no estrato {STRATUM_RULE} com everton_pick=true, \
ocupa a vaga da regra e não cria vaga extra.
11. Quadro obrigatório completo = {BOARD_ROWS} linhas legíveis em cada uma das 6 visões, sem \
linha malformada. Quadro incompleto, parada (401, 403 ou 429) ou orçamento esgotado antes do \
fim dos 6 quadros = nenhuma seleção. Lista gravada é imutável; outra seleção nasce como outra \
coorte (--new-cohort), que aponta para a anterior."""

RULE_SHA256 = hashlib.sha256(RULE_TEXT.encode("utf-8")).hexdigest()
__doc__ = f"{__doc__}\n{RULE_TEXT}\n"

_BASE58 = re.compile(r"[1-9A-HJ-NP-Za-km-z]{32,44}")


@dataclass(frozen=True, slots=True)
class Evaluation:
    address: str
    reject_reason: str | None
    score: Decimal | None
    periods: int
    rows: Sequence[BoardRow]


@dataclass(slots=True)
class Leader:
    address: str
    stratum: str
    rule_selected: bool
    rule_rank: int | None
    everton_pick: bool
    boards: list[str]
    reference_board: str | None
    realized_pnl_sol: Decimal | None
    unrealized_pnl_sol: Decimal | None
    buy_spend_sol: Decimal | None
    positions_count: int | None
    positions_per_day: Decimal | None
    realized_share: Decimal | None
    is_verified: bool | None
    last_refreshed_at_ms: int | None
    score: Decimal | None
    positions_realized_boards: dict[str, int | None]


@dataclass(frozen=True, slots=True)
class Selection:
    leaders: list[Leader]
    evaluated: list[Evaluation]
    funnel: dict[str, int]
    universe_wallets: int


def is_solana_address(address: str) -> bool:
    return _BASE58.fullmatch(address) is not None


def validate_includes(addresses: Iterable[str]) -> list[str]:
    unique = sorted(set(addresses))  # canonical order: the same set freezes the same list
    for address in unique:
        if not is_solana_address(address):
            raise RuleError(f"--include {address!r} is not a Solana address (base58, 32-44 chars)")
    if len(unique) > MAX_INCLUDES:
        raise RuleError(f"at most {MAX_INCLUDES} --include addresses fit the 30-request budget")
    return unique


def _reference(rows: Sequence[BoardRow]) -> BoardRow:
    for period in PERIODS_LONGEST_FIRST:
        for sort in SORTS:
            for row in rows:
                if row.period == period and row.sort == sort:
                    return row
    raise AssertionError("a wallet has at least one row")


def _share(realized: Decimal, unrealized: Decimal) -> Decimal:
    return realized / (realized + max(unrealized, Decimal(0)))


def _first_failure(address: str, rows: Sequence[BoardRow], ref: BoardRow) -> str | None:
    if not is_solana_address(address):
        return "not_solana"
    if len({r.period for r in rows}) < MIN_PERIODS:
        return "one_period"
    if any(r.realized_pnl_sol <= 0 for r in rows):
        return "realized_not_positive"
    if ref.buy_spend_sol <= 0:
        return "no_cost_basis"
    if _share(ref.realized_pnl_sol, ref.unrealized_pnl_sol) < MIN_REALIZED_SHARE:
        return "mostly_unrealized"
    if ref.realized_pnl_sol + ref.unrealized_pnl_sol <= 0:
        return "net_not_positive"
    if ref.positions_count < MIN_POSITIONS:
        return "too_few_positions"
    return None


def _realized_positions(rows: Sequence[BoardRow]) -> dict[str, int | None]:
    found = {r.period: r.position for r in rows if r.sort == "realized"}
    return {period: found.get(period) for period in PERIOD_DAYS}


def _score(positions: Mapping[str, int | None]) -> Decimal:
    values = [MISSING_POSITION if p is None else p for p in positions.values()]
    return Decimal(sum(values)) / Decimal(len(values))


def _leader(
    address: str,
    rows: Sequence[BoardRow],
    *,
    stratum: str,
    rank: int | None,
    selected: bool,
    everton_pick: bool,
) -> Leader:
    positions = _realized_positions(rows)
    ref = _reference(rows) if rows else None
    return Leader(
        address=address,
        stratum=stratum,
        rule_selected=selected,
        rule_rank=rank,
        everton_pick=everton_pick,
        boards=sorted({f"{r.period}:{r.sort}" for r in rows}),
        reference_board=f"{ref.period}:{ref.sort}" if ref else None,
        realized_pnl_sol=ref.realized_pnl_sol if ref else None,
        unrealized_pnl_sol=ref.unrealized_pnl_sol if ref else None,
        buy_spend_sol=ref.buy_spend_sol if ref else None,
        positions_count=ref.positions_count if ref else None,
        positions_per_day=(
            Decimal(ref.positions_count) / Decimal(PERIOD_DAYS[ref.period]) if ref else None
        ),
        realized_share=(
            _share(ref.realized_pnl_sol, ref.unrealized_pnl_sol)
            if ref and ref.realized_pnl_sol > 0
            else None
        ),
        is_verified=ref.is_verified if ref else None,
        last_refreshed_at_ms=ref.last_refreshed_at_ms if ref else None,
        score=_score(positions) if rows else None,
        positions_realized_boards=positions,
    )


def select(boards: Sequence[ParsedBoard], includes: Sequence[str]) -> Selection:
    """Apply the frozen rule; ``includes`` must already be validated."""
    by_wallet: dict[str, list[BoardRow]] = {}
    for board in boards:
        for row in board.rows:
            by_wallet.setdefault(row.address, []).append(row)

    evaluated: list[Evaluation] = []
    eligible: list[tuple[Decimal, str]] = []
    funnel: dict[str, int] = {"wallets_seen": len(by_wallet)}
    for address, rows in sorted(by_wallet.items()):
        reason = _first_failure(address, rows, _reference(rows))
        score = _score(_realized_positions(rows))
        evaluated.append(Evaluation(address, reason, score, len({r.period for r in rows}), rows))
        if reason is None:
            eligible.append((score, address))
        else:
            funnel[f"rejected_{reason}"] = funnel.get(f"rejected_{reason}", 0) + 1
    funnel["eligible"] = len(eligible)

    eligible.sort()
    top = [address for _, address in eligible[:TOP_N]]
    funnel["rule_selected"] = len(top)

    leaders = [
        _leader(
            address,
            by_wallet[address],
            stratum=STRATUM_RULE,
            rank=rank,
            selected=True,
            everton_pick=address in includes,
        )
        for rank, address in enumerate(top, start=1)
    ]
    leaders.extend(
        _leader(
            address,
            by_wallet.get(address, []),
            stratum=STRATUM_EVERTON,
            rank=None,
            selected=False,
            everton_pick=True,
        )
        for address in includes
        if address not in top
    )
    funnel["includes"] = len(includes)
    return Selection(leaders, evaluated, funnel, len(by_wallet))
