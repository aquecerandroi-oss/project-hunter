"""Normalized shapes of the site's own surfaces (T4.2c): a board entry of
``/ws/trenches`` (and its HTTP twin ``/boards/{board}``), the rug-risk read of
``/in-memory-coin/{mint}`` and a trade of ``swap-api.pump.fun``.

Same discipline as ``models.py``: frozen, ``extra="forbid"``, every number a
``Decimal``, every instant UTC-aware. ``observed_at`` is the **source's** clock
(``serverTs`` of the board message, the trade's block ``timestamp``) and
``received_at`` is ours — the ``ts``/``received_at`` split of
``docs/EXCHANGE_INTEGRATION.md`` §2, which these sources, unlike PumpPortal's
frames, actually carry.

**Short keys stay inside this package.** The board wire format uses two-letter
keys (``nh``, ``t10``, ``dh``, ``sn``…, measured live on 2026-09-12 and kept in
``tests/fixtures/pumpfun/trenches_*.json``); ``trenches_state.py`` is the one
place that reads them, and what leaves is the long name. Keys whose meaning was
not established (``ic``, ``so``, ``bo``, ``ih``, ``rid``) travel in ``extra``,
labelled raw, never renamed into a claim.

**Percentages become fractions once.** ``t10``/``dh`` arrive as ``77.3048``
(a percent) and ``top10HoldersPercent`` likewise; every ``*_share`` below is the
fraction ``0.773048`` so ``meme_features_1m.top10_share`` (``NUMERIC(9,6)``, a
fraction by CHECK) reads the same number the API renders.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field, field_validator

from hunter_core.domain.types import ensure_utc
from hunter_exchanges.pumpfun.models import ReceivedAtMixin

BOARDS: tuple[str, ...] = ("new", "graduating", "graduated", "movers")
"""``PRO_SCREENER_BOARDS`` of the site's bundle (``docs/PUMPFUN.md`` §3.1)."""

TRENCHES_SOURCE = "trenches_ws"
BOARDS_REST_SOURCE = "indexer_rest:/boards"
RISK_SOURCE = "indexer_rest:/in-memory-coin"
SWAP_API_SOURCE = "swap_api"


class NormalizedBoardEntry(ReceivedAtMixin):
    """One coin as one board of the screener shows it at one instant.

    ``position`` is the row's index on the board (``0`` = top), ``version`` the
    board version the entry was last patched at. ``observed_at`` is the
    message's ``serverTs``. A field the wire did not carry is ``None`` — the
    boards do not send every key for every chain (``movers`` lists EVM coins
    with no ``pa``), and an absent key is not a zero.
    """

    kind: Literal["meme_board_entry"] = "meme_board_entry"
    board: str
    position: int
    version: int
    mint: str
    chain: str | None = None
    """``solana:mainnet`` or an EVM ``eip155:*`` — the ``movers`` board mixes
    chains, and only the first is this adapter's venue."""
    program: str | None = None
    """``pump`` for a pump.fun bonding curve; ``raydium_launchpad``, ``pons``…
    observed live. Only ``pump`` is the curve this project trades in paper."""
    platform: str | None = None
    quote_asset: str | None = None
    """``SOL`` (``pa``); the USDC-paired coins of 2026-05-21 read otherwise."""
    name: str | None = None
    symbol: str | None = None
    image_uri: str | None = None
    description: str | None = None
    market_cap_usd: Decimal | None = None
    progress_pct: Decimal | None = None
    """Curve progress in **percent** as the site shows it (``100`` once graduated)."""
    volume_sol: Decimal | None = None
    volume_usd: Decimal | None = None
    volume_5m_sol: Decimal | None = None
    volume_15m_sol: Decimal | None = None
    volume_1h_sol: Decimal | None = None
    volume_24h_sol: Decimal | None = None
    volume_5m_usd: Decimal | None = None
    volume_15m_usd: Decimal | None = None
    volume_1h_usd: Decimal | None = None
    volume_24h_usd: Decimal | None = None
    tx_5m: int | None = None
    age_s: int | None = None
    """Seconds since creation (``age``; a coin 102 s old graduated 101 s ago in
    the live capture — the same-slot graduations of the plantão)."""
    kol_count: int | None = None
    snipers: int | None = None
    is_mayhem: bool | None = None
    mayhem_state: str | None = None
    has_social: bool | None = None
    has_twitter: bool | None = None
    has_website: bool | None = None
    has_telegram: bool | None = None
    graduated_at: datetime | None = None
    """``gd`` (epoch ms); ``0`` on the wire means *not graduated* and is ``None``."""
    ath_market_cap_usd: Decimal | None = None
    buys: int | None = None
    sells: int | None = None
    txs: int | None = None
    holders: int | None = None
    top10_share: Decimal | None = None
    dev_share: Decimal | None = None
    cashback: bool | None = None
    dev_wallet: str | None = None
    is_live: bool | None = None
    participants: int | None = None
    fees_sol: Decimal | None = None
    fees_usd: Decimal | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
    """Short keys this adapter does not interpret (``ic``, ``so``, ``bo``, ``ih``,
    ``rid``): kept raw and labelled, never promoted to a column by guess."""
    source: str = TRENCHES_SOURCE

    @field_validator("graduated_at", mode="after")
    @classmethod
    def _graduated_at_is_utc(cls, v: datetime | None) -> datetime | None:
        return None if v is None else ensure_utc(v)

    @property
    def is_pump_curve_on_sol(self) -> bool:
        """The only entries the radar tracks: pump.fun's program, native SOL."""
        return self.program == "pump" and self.quote_asset == "SOL"


class NormalizedRiskSnapshot(ReceivedAtMixin):
    """``GET /in-memory-coin/{mint}`` — 65 undocumented fields, the richest
    public rug-risk read (``docs/PUMPFUN.md`` §3.1). ``raw`` is the whole
    object, labelled; the columns beside it are the few whose meaning the
    key names state and the radar stores next to the row."""

    kind: Literal["meme_risk_snapshot"] = "meme_risk_snapshot"
    mint: str
    program: str | None = None
    platform: str | None = None
    quote_mint: str | None = None
    quote_asset: str | None = None
    holders: int | None = None
    top10_share: Decimal | None = None
    dev_share: Decimal | None = None
    snipers: int | None = None
    sniper_share: Decimal | None = None
    bundled_share: Decimal | None = None
    progress_pct: Decimal | None = None
    graduated_at: datetime | None = None
    is_mayhem: bool | None = None
    mayhem_state: str | None = None
    raw: dict[str, Any]
    source: str = RISK_SOURCE

    @field_validator("graduated_at", mode="after")
    @classmethod
    def _graduated_at_is_utc(cls, v: datetime | None) -> datetime | None:
        return None if v is None else ensure_utc(v)


class NormalizedSwapTrade(ReceivedAtMixin):
    """One row of ``GET swap-api /v2/coins/{mint}/trades``.

    ``observed_at`` is the trade's block ``timestamp``. ``slot`` is the first
    twelve digits of ``slotIndexId`` — verified against ``getTransaction`` on
    2026-09-12 (``rpc_get_transaction_slot_evidence_raw.json``: id
    ``000446373814…`` → slot ``446373814``, block time equal to the timestamp).
    The remaining digits are an undocumented ordering key; they are kept raw
    in ``slot_index_id`` and never decoded into an instruction index.
    """

    kind: Literal["meme_swap_trade"] = "meme_swap_trade"
    mint: str
    signature: str
    slot_index_id: str
    slot: int
    trader: str
    side: Literal["buy", "sell"]
    program: str
    is_bonding_curve: bool
    """``program == "pump"``: a trade against the curve, not the PumpSwap pool
    (``pump_amm``) nor another launchpad's AMM (``raydium_cpmm``, observed live)."""
    quote_is_native_sol: bool
    """``quoteAmount == amountSol`` **and** lamport-exact: the quote leg is SOL
    itself, not a converted USD/USDC figure. False on the ``raydium_cpmm`` rows of
    the live capture, whose ``amountSol`` carries 28 decimals of conversion."""
    sol_amount: Decimal
    sol_lamports: int | None
    """Exact base units when ``quote_is_native_sol``; ``None`` otherwise."""
    token_amount: Decimal
    price: Decimal
    """``fillPriceSol`` — SOL paid per token on *this* fill (``amountSol /
    baseAmount``), the contract's ``sol_amount / token_amount`` at event time."""
    marginal_price: Decimal | None = None
    """``priceSol`` — the curve's marginal price after the fill, when sent."""
    amount_usd: Decimal | None = None
    source: str = SWAP_API_SOURCE


__all__ = [
    "BOARDS",
    "BOARDS_REST_SOURCE",
    "RISK_SOURCE",
    "SWAP_API_SOURCE",
    "TRENCHES_SOURCE",
    "NormalizedBoardEntry",
    "NormalizedRiskSnapshot",
    "NormalizedSwapTrade",
]
