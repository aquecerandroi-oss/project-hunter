"""Pure readers of the raw JSONB a real fill/decision tape carries (T4.92).

Split out of ``meme_daily_ficha_queries.py`` to keep it under the file-size
budget and because this is one responsibility on its own: turning the chain's
own JSON shapes into ``Decimal``/``int`` values, or ``None`` when a real
number cannot be proven — never a guessed zero. No database import here, no
clock; every function takes the row's own dict and returns a value.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any, cast

__all__ = [
    "LAMPORTS",
    "fees_sol",
    "fraction_to_pct",
    "rent_refund_sol",
    "round_trip_cost_sol",
    "sol_from_lamports",
    "tape_features",
]

LAMPORTS = Decimal(1_000_000_000)


def sol_from_lamports(lamports: int | None) -> Decimal | None:
    return None if lamports is None else Decimal(lamports) / LAMPORTS


def fraction_to_pct(value: Decimal | None) -> Decimal | None:
    """Some ``meme_features_1m`` columns (``curve_progress_pct``, ``dev_share``)
    are fractions in ``[0, 1]`` despite the ``_pct`` name (Astra, T4.92 review,
    HIGH: ``curve_progress_pct`` is documented "``1 - real/initial`` as a
    fraction", and ``dev_share`` has the DB CHECK
    ``ck_meme_features_1m_dev_share_is_a_fraction``) — multiplied by 100 here
    so a caller always gets an actual percentage, the render's own convention
    for ``pnl_pct``/``peak_pct``."""
    return None if value is None else value * 100


def fees_sol(fill: Mapping[str, Any] | None) -> Decimal | None:
    """The fee legs of one confirmed fill, in SOL — ``None`` when there is no
    fill, or a real fee this ficha cannot prove, to read (the position's own
    honesty, never a guessed zero).

    Two shapes exist (Astra, T4.92 review, HIGH): a curve fill
    (``services/meme-executor/hunter_meme_executor/fills.py::FillRecord.as_json``)
    carries ``fee``/``creator_fee``; a PumpSwap fill (a migrated position's exit,
    ``pumpswap_build.py::PumpSwapFillRecord.as_json``, ``venue: "pumpswap"``)
    carries ``lp_fee``/``protocol_fee``/``coin_creator_fee`` instead — reading the
    curve's keys off a PumpSwap fill silently summed to a fee of zero."""
    if fill is None:
        return None
    network = fill.get("network_fee_lamports")
    keys = (
        ("lp_fee", "protocol_fee", "coin_creator_fee")
        if fill.get("venue") == "pumpswap"
        else ("fee", "creator_fee")
    )
    parts = [fill.get(key) for key in keys]
    if network is None or any(part is None for part in parts):
        return None
    known_parts = cast(list[int], parts)
    return (sum(Decimal(part) for part in known_parts) + Decimal(cast(int, network))) / LAMPORTS


def rent_refund_sol(exit_fill: Mapping[str, Any] | None) -> Decimal | None:
    if exit_fill is None:
        return None
    refund = exit_fill.get("ata_rent_refund_lamports")
    return None if refund is None else Decimal(refund) / LAMPORTS


def round_trip_cost_sol(
    entry_fees: Decimal | None, exit_fees: Decimal | None, rent_refund: Decimal | None
) -> Decimal | None:
    if entry_fees is None or exit_fees is None:
        return None
    return entry_fees + exit_fees - (rent_refund or Decimal(0))


def tape_features(
    derived: Mapping[str, Any] | None,
) -> tuple[int | None, int | None, int | None, Decimal | None, Decimal | None, int | None]:
    """``buys_1m, sells_1m, unique_buyers, net_flow_sol, creation_bundle_sol,
    creation_bundle_wallets`` from ``meme_decision_tapes.derived`` — every value
    ``None`` when there is no tape row for this instant (event lane only, or
    ``MEME_DECISION_TAPE=off``)."""
    if derived is None:
        return None, None, None, None, None, None
    windows = derived.get("windows")
    window = cast(dict[str, Any], windows).get("60s") if isinstance(windows, dict) else None
    buys = sells = unique_buyers = net_flow = None
    if isinstance(window, dict) and "reason" not in window:
        window = cast(dict[str, Any], window)
        buys, sells, unique_buyers = (
            window.get("buys"),
            window.get("sells"),
            window.get("unique_buyers"),
        )
        net_sol = window.get("net_sol")
        net_flow = None if net_sol is None else Decimal(str(net_sol))
    bundle = derived.get("creation_bundle")
    bundle_sol = bundle_wallets = None
    if isinstance(bundle, dict):
        bundle = cast(dict[str, Any], bundle)
        sol = bundle.get("sol")
        bundle_sol = None if sol is None else Decimal(str(sol))
        bundle_wallets = bundle.get("wallets")
    return buys, sells, unique_buyers, net_flow, bundle_sol, bundle_wallets
