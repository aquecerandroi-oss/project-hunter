"""Typed shapes of the Jupiter v6 aggregator's public quote/swap API (T4.54).

Amounts are ``Decimal`` atoms (the smallest unit of the mint — 6 decimals for
USDC, 9 for wrapped SOL), matching every other number this codebase carries.
Nothing here signs or sends anything; :class:`JupiterSwapTransaction` is an
unsigned, base64-encoded versioned transaction the caller must still verify
(``hunter_meme_executor.treasury``) and sign before it means anything.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

__all__ = ["JupiterQuote", "JupiterSwapTransaction"]

WRAPPED_SOL_MINT = "So11111111111111111111111111111111111111112"


@dataclass(frozen=True, slots=True)
class JupiterQuote:
    """One ``GET /v6/quote`` reply — parsed fields plus the raw JSON body.

    ``raw`` is carried unmodified because ``POST /v6/swap`` wants the *whole*
    quote object back as ``quoteResponse``, byte for byte, not our own
    reconstruction of it.
    """

    input_mint: str
    output_mint: str
    in_amount: Decimal
    out_amount: Decimal
    other_amount_threshold: Decimal
    price_impact_pct: Decimal
    slippage_bps: int
    route_labels: tuple[str, ...]
    """The AMMs the route crosses (``routePlan[*].swapInfo.label``), for logs
    and refusals only — never re-derived into an instruction."""

    raw: Mapping[str, Any]

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> JupiterQuote:
        route_plan = cast("list[Any]", payload.get("routePlan") or [])
        labels: list[str] = []
        for entry in route_plan:
            if not isinstance(entry, Mapping):
                continue
            entry_map = cast("Mapping[str, Any]", entry)
            swap_info = cast("Mapping[str, Any]", entry_map.get("swapInfo") or {})
            labels.append(str(swap_info.get("label", "")))
        return cls(
            input_mint=str(payload["inputMint"]),
            output_mint=str(payload["outputMint"]),
            in_amount=Decimal(str(payload["inAmount"])),
            out_amount=Decimal(str(payload["outAmount"])),
            other_amount_threshold=Decimal(str(payload["otherAmountThreshold"])),
            price_impact_pct=Decimal(str(payload.get("priceImpactPct", "0"))),
            slippage_bps=int(cast("int", payload.get("slippageBps", 0))),
            route_labels=tuple(labels),
            raw=payload,
        )


@dataclass(frozen=True, slots=True)
class JupiterSwapTransaction:
    """One ``POST /v6/swap`` reply: an unsigned, base64 versioned transaction."""

    swap_transaction_b64: str
    last_valid_block_height: int | None
    prioritization_fee_lamports: int | None

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> JupiterSwapTransaction:
        fee = payload.get("prioritizationFeeLamports")
        return cls(
            swap_transaction_b64=str(payload["swapTransaction"]),
            last_valid_block_height=(
                None
                if payload.get("lastValidBlockHeight") is None
                else int(payload["lastValidBlockHeight"])
            ),
            prioritization_fee_lamports=None if not isinstance(fee, int) else fee,
        )
