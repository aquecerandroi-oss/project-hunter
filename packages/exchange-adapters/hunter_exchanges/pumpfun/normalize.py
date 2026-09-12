"""Pure raw -> ``Normalized*`` parsing. No I/O, no clock other than ``utcnow``.

Every function here is the single place a raw pump.fun/PumpPortal/Solana
field name is read (``docs/EXCHANGE_INTEGRATION.md`` §2's "no raw field
leaks out" rule, applied to this package's own boundary).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, cast

from hunter_core.domain.types import utcnow
from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.pumpfun.curve import (
    market_cap_sol,
    raw_lamports_to_sol,
    raw_subunits_to_tokens,
)
from hunter_exchanges.pumpfun.decode import NATIVE_SOL_QUOTE_MINT, BondingCurveAccount
from hunter_exchanges.pumpfun.models import (
    NormalizedCurveState,
    NormalizedMemeMigration,
    NormalizedMemeTokenCreated,
)


class UnsupportedQuote(MalformedMessage):
    """The curve is quoted in something other than native SOL (a USDC pair of
    2026-05-21): not malformed, just not this adapter's venue. A caller that
    keeps polling such a mint spends budget on a curve it will never read —
    the 2–4 wasted requests a minute the T4.2c adendo measured — so the type
    exists for the collector to stop tracking it by name."""

    def __init__(self, mint: str | None = None) -> None:
        super().__init__("curve quote must be native SOL", exchange="pumpfun")
        self.mint = mint


#: The only ``pool`` value PumpPortal reports for an actual pump.fun bonding
#: curve create event (observed live: ``"bonk"`` also flows through the same
#: ``subscribeNewToken`` method for letsbonk.fun — a different program this
#: package never claims to speak for).
PUMP_POOL = "pump"

#: Migration destination pool label PumpPortal reports for PumpSwap
#: (observed live; T4-MEME-RADAR.md §3 confirms migration targets PumpSwap
#: today).
PUMPSWAP_POOL = "pump-amm"

_REQUIRED_CREATE_FIELDS = (
    "signature",
    "mint",
    "name",
    "symbol",
    "uri",
    "traderPublicKey",
    "bondingCurveKey",
    "vSolInBondingCurve",
    "vTokensInBondingCurve",
    "pool",
)
_REQUIRED_MIGRATE_FIELDS = ("signature", "mint", "pool")


def _decimal(value: Any, field: str) -> Decimal:
    """Preserve JSON decimal digits; callers must decode with parse_float=Decimal."""
    if not isinstance(value, (int, Decimal)) or isinstance(value, bool):
        raise MalformedMessage(
            f"pumpportal field {field!r} is not a number: {value!r}", exchange="pumpfun"
        )
    try:
        result = Decimal(value)
        if not result.is_finite() or result < 0:
            raise InvalidOperation
        return result
    except InvalidOperation as exc:
        raise MalformedMessage(
            f"pumpportal field {field!r} is not decimal: {value!r}", exchange="pumpfun"
        ) from exc


def _require(raw: dict[str, Any], fields: tuple[str, ...], kind: str) -> None:
    missing = [f for f in fields if f not in raw]
    if missing:
        raise MalformedMessage(f"pumpportal {kind} message missing {missing}", exchange="pumpfun")
    for field in fields:
        if field not in ("vSolInBondingCurve", "vTokensInBondingCurve"):
            if not isinstance(raw[field], str) or (
                field not in ("name", "symbol", "uri") and not raw[field]
            ):
                raise MalformedMessage(f"invalid text field: {field}", exchange="pumpfun")


def is_new_token_message(raw: dict[str, Any]) -> bool:
    """``subscribeNewToken`` sends ``txType: "create"`` for both real creates
    and (rarely, in this task's own live capture) a second creation-flavored
    frame with a different, thinner shape (see ``ws.py`` for why those are
    skipped, not force-parsed)."""
    return raw.get("txType") == "create"


def is_migration_message(raw: dict[str, Any]) -> bool:
    return raw.get("txType") == "migrate"


def is_in_scope_pool(pool: str) -> bool:
    """Only pump.fun's own bonding curve program is in scope for this adapter."""
    return pool == PUMP_POOL


def parse_new_token(raw: dict[str, Any]) -> NormalizedMemeTokenCreated:
    """``subscribeNewToken`` raw frame -> :class:`NormalizedMemeTokenCreated`.

    Raises :class:`MalformedMessage` for a required field missing (a
    genuinely malformed frame) — callers decide separately whether to skip a
    frame whose ``pool`` is out of scope (:func:`is_in_scope_pool`), which is
    not malformed, just not this adapter's program.
    """
    _require(raw, _REQUIRED_CREATE_FIELDS, "create")
    pool = raw["pool"]
    if not is_in_scope_pool(pool):
        raise ValueError(
            f"pool {pool!r} is out of scope for parse_new_token; check is_in_scope_pool() first"
        )
    now = utcnow()
    return NormalizedMemeTokenCreated(
        mint=str(raw["mint"]),
        name=str(raw["name"]),
        symbol=str(raw["symbol"]),
        uri=str(raw["uri"]),
        creator=str(raw["traderPublicKey"]),
        created_at=now,
        bonding_curve=str(raw["bondingCurveKey"]),
        initial_virtual_sol_reserves=_decimal(raw["vSolInBondingCurve"], "vSolInBondingCurve"),
        initial_virtual_token_reserves=_decimal(
            raw["vTokensInBondingCurve"], "vTokensInBondingCurve"
        ),
        signature=str(raw["signature"]),
        pool=pool,
        received_at=now,
        observed_at=now,
        mayhem_enabled=_optional_bool(raw.get("is_mayhem_mode", raw.get("mayhem_enabled"))),
        mayhem_mode=_optional_text(raw.get("mayhem_mode")),
    )


def parse_migration(raw: dict[str, Any]) -> NormalizedMemeMigration:
    _require(raw, _REQUIRED_MIGRATE_FIELDS, "migrate")
    now = utcnow()
    return NormalizedMemeMigration(
        mint=str(raw["mint"]),
        pool=str(raw["pool"]),
        migrated_at=now,
        signature=str(raw["signature"]),
        received_at=now,
        observed_at=now,
    )


def _optional_bool(value: Any) -> bool | None:
    if value is not None and not isinstance(value, bool):
        raise MalformedMessage("invalid mayhem boolean", exchange="pumpfun")
    return value


def _optional_text(value: Any) -> str | None:
    if value is not None and not isinstance(value, str):
        raise MalformedMessage("invalid mayhem text", exchange="pumpfun")
    return value


def parse_curve_state_rest(raw: dict[str, Any]) -> NormalizedCurveState:
    """``frontend-api-v3.pump.fun`` ``/coins/...`` entry -> :class:`NormalizedCurveState`.

    Every reserve field on this endpoint is a raw integer (lamports /
    6-decimal token subunits, confirmed live — T4.0 §2), same wire format as
    the RPC account.
    """
    required = (
        "mint",
        "virtual_sol_reserves",
        "virtual_token_reserves",
        "real_sol_reserves",
        "real_token_reserves",
        "total_supply",
        "complete",
    )
    missing = [f for f in required if f not in raw]
    if missing:
        raise MalformedMessage(f"pumpfun rest curve response missing {missing}", exchange="pumpfun")
    if raw.get("quote_mint") != NATIVE_SOL_QUOTE_MINT:
        raise UnsupportedQuote(str(raw.get("mint")))
    if raw.get("base_decimals", 6) != 6 or raw.get("quote_decimals", 9) != 9:
        raise MalformedMessage("unsupported curve decimals", exchange="pumpfun")
    if not isinstance(raw["complete"], bool):
        raise MalformedMessage("complete must be boolean", exchange="pumpfun")
    for field in required[1:-1]:
        if type(raw[field]) is not int or raw[field] < 0:
            raise MalformedMessage(f"invalid integer reserve: {field}", exchange="pumpfun")
    if raw["virtual_token_reserves"] == 0:
        raise MalformedMessage("virtual token reserve must be positive", exchange="pumpfun")
    mayhem_raw: Any = raw.get("mayhem") or {}
    if not isinstance(mayhem_raw, dict):
        raise MalformedMessage("invalid mayhem object", exchange="pumpfun")
    mayhem = cast(dict[str, Any], mayhem_raw)
    virtual_sol = raw_lamports_to_sol(int(raw["virtual_sol_reserves"]))
    virtual_token = raw_subunits_to_tokens(int(raw["virtual_token_reserves"]))
    total_supply = raw_subunits_to_tokens(int(raw["total_supply"]))
    now = utcnow()
    return NormalizedCurveState(
        mint=str(raw["mint"]),
        virtual_sol_reserves=virtual_sol,
        virtual_token_reserves=virtual_token,
        real_sol_reserves=raw_lamports_to_sol(int(raw["real_sol_reserves"])),
        real_token_reserves=raw_subunits_to_tokens(int(raw["real_token_reserves"])),
        total_supply=total_supply,
        complete=bool(raw["complete"]),
        market_cap_sol=market_cap_sol(virtual_sol, virtual_token, total_supply),
        observed_at=now,
        source="pumpfun_rest",
        mayhem_enabled=_optional_bool(raw.get("is_mayhem_mode", raw.get("mayhem_enabled"))),
        mayhem_state=_optional_text(raw.get("mayhem_state", mayhem.get("state"))),
        mayhem_mode=_optional_text(raw.get("mayhem_mode", mayhem.get("mode"))),
        received_at=now,
    )


def curve_state_from_rpc_account(mint: str, account: BondingCurveAccount) -> NormalizedCurveState:
    """Decoded on-chain :class:`BondingCurveAccount` -> :class:`NormalizedCurveState`.

    The on-chain truth (T4-MEME-RADAR.md §2: "verdade de base" is the
    program's own ledger) — ``source="solana_rpc"`` lets a consumer prefer
    this over the best-effort REST mirror.
    """
    if account.quote_mint != NATIVE_SOL_QUOTE_MINT:
        raise UnsupportedQuote(mint)
    if account.virtual_token_reserves == 0:
        raise MalformedMessage("empty virtual reserve", exchange="pumpfun")
    virtual_sol = raw_lamports_to_sol(account.virtual_sol_reserves)
    virtual_token = raw_subunits_to_tokens(account.virtual_token_reserves)
    total_supply = raw_subunits_to_tokens(account.token_total_supply)
    now = utcnow()
    return NormalizedCurveState(
        mint=mint,
        virtual_sol_reserves=virtual_sol,
        virtual_token_reserves=virtual_token,
        real_sol_reserves=raw_lamports_to_sol(account.real_sol_reserves),
        real_token_reserves=raw_subunits_to_tokens(account.real_token_reserves),
        total_supply=total_supply,
        complete=account.complete,
        market_cap_sol=market_cap_sol(virtual_sol, virtual_token, total_supply),
        observed_at=now,
        source="solana_rpc",
        mayhem_enabled=account.is_mayhem_mode,
        received_at=now,
    )


__all__ = [
    "PUMPSWAP_POOL",
    "PUMP_POOL",
    "UnsupportedQuote",
    "curve_state_from_rpc_account",
    "is_in_scope_pool",
    "is_migration_message",
    "is_new_token_message",
    "parse_curve_state_rest",
    "parse_migration",
    "parse_new_token",
]
