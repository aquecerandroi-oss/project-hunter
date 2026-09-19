"""Pure rendering of one ``spot/1`` position into the operator's Markdown
ficha and its one line on the desk's scoreboard (design
``docs/design/spot1-lab-solana.md`` §7; T4.74-6).

Nothing here touches a database or the filesystem — ``spot_ficha.py`` reads
the row, this module turns it into text, byte for byte the same on every
call for the same input (the idempotency the scoreboard append relies on).
A field the row does not carry is printed ``indisponível``, never guessed or
zeroed (the project's doctrine: a missing input is not a zero).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

__all__ = [
    "OrderView",
    "PositionView",
    "ficha_filename",
    "position_id8",
    "render_ficha",
    "scoreboard_line",
]

_INDISPONIVEL = "indisponível"


@dataclass(frozen=True, slots=True)
class OrderView:
    side: str
    status: str
    tx_signature: str | None
    admission: dict[str, Any] = field(default_factory=dict[str, Any])


@dataclass(frozen=True, slots=True)
class PositionView:
    """Everything ``spot_ficha.py`` reads for one ``spot_positions`` row."""

    id: str
    market_symbol: str
    mint: str
    base: str
    kind: str
    status: str
    entry_at: datetime
    entry: dict[str, Any]
    tokens: int
    sol_spent_lamports: int
    initial_risk_sol: Decimal
    params: dict[str, Any]
    ata_rent_lamports: int
    mark_sol: Decimal | None
    mark_reason: str | None
    exit_at: datetime | None
    exit: dict[str, Any] | None
    sol_received_lamports: int | None
    pnl_sol: Decimal | None
    r_multiple: Decimal | None
    entry_order: OrderView | None
    exit_order: OrderView | None


def position_id8(position_id: str) -> str:
    return position_id.replace("-", "")[:8]


def ficha_filename(view: PositionView) -> str:
    day = view.entry_at.date().isoformat()
    return f"Ficha-{day}-{view.market_symbol}-{position_id8(view.id)}.md"


def _fmt(value: Decimal | int | None) -> str:
    if value is None:
        return _INDISPONIVEL
    if isinstance(value, int):
        return str(value)
    return format(value.normalize(), "f")


def _jsonb_lines(payload: dict[str, Any] | None) -> str:
    if not payload:
        return "- (vazio)"
    return "\n".join(f"- `{key}`: {value}" for key, value in sorted(payload.items()))


def _decimal_or_none(payload: dict[str, Any], key: str) -> Decimal | None:
    value = payload.get(key)
    return None if value is None else Decimal(str(value))


def _parity(params: dict[str, Any]) -> str:
    jup, binp = (
        _decimal_or_none(params, "jup_usd_at_entry"),
        _decimal_or_none(params, "bin_usd_at_entry"),
    )
    if jup is None or binp is None or binp == 0:
        return _INDISPONIVEL
    desvio = (jup / binp - 1) * 100
    return f"jup_usd={_fmt(jup)} bin_usd={_fmt(binp)} desvio={_fmt(desvio)}%"


def _cost_r_from_admission(order: OrderView | None) -> Decimal | None:
    """§3's ``cost_r`` check, as ``evaluate_spot_entry`` recorded it on the
    entry order's admission — the fraction of R the round trip is expected to
    cost, read back rather than recomputed (the check ran once, at entry)."""
    if order is None:
        return None
    for check in order.admission.get("checks", []):
        if check.get("name") == "cost_r" and check.get("value") is not None:
            return Decimal(str(check["value"]))
    return None


def _r_bruto_liquido(view: PositionView) -> tuple[str, str]:
    liquido = (
        _fmt(view.r_multiple) if view.status == "closed" else "aberta (posição ainda não fechou)"
    )
    cost = _cost_r_from_admission(view.entry_order)
    if view.r_multiple is not None and cost is not None:
        bruto = _fmt(view.r_multiple + cost)
    else:
        bruto = "indisponível: falta admission.checks.cost_r no pedido de entrada"
    return bruto, liquido


def _signature_line(label: str, order: OrderView | None) -> str:
    if order is None:
        return f"- {label}: ainda não existe"
    sig = order.tx_signature or f"sem assinatura (status {order.status})"
    return f"- {label} ({order.side}, {order.status}): `{sig}`"


def render_ficha(view: PositionView) -> str:
    ref, stop_frac = (
        _decimal_or_none(view.params, "ref"),
        _decimal_or_none(view.params, "stop_frac"),
    )
    target_frac, horizon_s = (
        _decimal_or_none(view.params, "target_frac"),
        view.params.get("horizon_s"),
    )
    sol_usd_entry = _decimal_or_none(view.params, "sol_usd_at_entry")
    sol_usd_exit = _decimal_or_none(view.exit or {}, "sol_usd_at_exit")
    bruto, liquido = _r_bruto_liquido(view)
    return f"""# Ficha — {view.market_symbol} ({position_id8(view.id)})

`spot_positions.id` = `{view.id}` · mint `{view.mint}` ({view.base}, {view.kind}) · status `{view.status}`
Entrada em `{view.entry_at.isoformat()}`{f" · saída em {view.exit_at.isoformat()}" if view.exit_at else ""}

## Sinal e geometria (design §4)
- `ref` = {_fmt(ref)}, `stop_frac` = {_fmt(stop_frac)}, `target_frac` = {_fmt(target_frac)}
- `horizon_s` = {horizon_s if horizon_s is not None else _INDISPONIVEL}
- `initial_risk_sol` (r_unit_sol) = {_fmt(view.initial_risk_sol)}
- tokens = {view.tokens}, sol_spent_lamports = {view.sol_spent_lamports}, \
ata_rent_lamports = {view.ata_rent_lamports}

## Cotação de entrada
{_jsonb_lines(view.entry)}

## Cotação de saída
{_jsonb_lines(view.exit) if view.exit else "- (posição aberta)"}

## Assinaturas
{_signature_line("compra", view.entry_order)}
{_signature_line("venda", view.exit_order)}

## Paridade na decisão (design §2)
- {_parity(view.params)}

## SOL/USD
- na entrada: {_fmt(sol_usd_entry)}
- na saída: {_fmt(sol_usd_exit)}

## Custo em R e resultado
- R bruto (antes das taxas de rede): {bruto}
- R líquido: {liquido}
- `pnl_sol`: {_fmt(view.pnl_sol)}
- `mark_sol`: {_fmt(view.mark_sol)}{f" ({view.mark_reason})" if view.mark_reason else ""}

## Lição
_(preencher à mão — o que esta operação ensinou)_
"""


def scoreboard_line(view: PositionView) -> str:
    """One row, plus the idempotency marker on its own line right after it
    (``obsidian/03-TRADING/Spot/Mesa-spot-1.md``, design §7)."""
    id8 = position_id8(view.id)
    day = view.entry_at.date().isoformat()
    _, liquido = _r_bruto_liquido(view)
    pnl = _fmt(view.pnl_sol)
    ficha_link = f"[[03-TRADING/Spot/{ficha_filename(view)[:-3]}|ficha]]"
    row = f"| {day} | {view.market_symbol} | {id8} | {view.status} | {liquido} | {pnl} | {ficha_link} |"
    return f"{row}\n<!-- {id8} -->"
