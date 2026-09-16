"""``FeeConfig`` of the pump.fun **fee program** — the fee schedule, read, not dated.

Since the 2026-09-12 upgrade (KB-0094) every ``buy``/``sell`` carries two extra
accounts: ``fee_config`` (this account) and ``fee_program``
(``pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ``). The program computes the fee
basis points from the account, falling back to ``Global`` only when the account
is absent. Until T4.29c this package carried a dated constant instead
(``quote.BONDING_CURVE_FEE_TIER_2026_05_20``, "Last Updated: 20 May 2026").

**Sources** (T4.29c, 2026-09-16, never from memory):

- layout: ``idl/pump_fees.json`` of ``pump-fun/pump-public-docs`` commit
  ``81091419e4457566469d4e2a27f64ed84d42419c`` (2026-09-14), file sha256
  ``d87b52305fd6b2ec487d4ba1e08a49990c23fa9b8b76092b2097df0164fa3859``;
  ``FeeConfig`` discriminator ``8f3492bbdb7b4c9b``. The fee program's own
  **on-chain** IDL account (``6hgWp61YgGzJ9QmvxyFtLnGfA8MYgx93Hby6fdq8gG31``,
  canonical sha256 ``37729b75d0891479c8cfb2d99857ad4fb5402dd1c3d28bf2aec74615292d99af``,
  read at slot 447 586 137) is **older**: 29 instructions and no
  ``exotic_flat_fees``. The live account bytes have the field, so the GitHub IDL
  is the one that describes the chain today; the field is decoded as optional.
- tier rule: ``docs/FEE_PROGRAM_README.md`` of the same commit, sha256
  ``c03c0cc79970456f9af1a54283d56bf8f752667dd95511640f42a4fb743cd72d``,
  function ``calculateFeeTier`` (``/// rust reference: pump-fees-math::calculate_fee_tier()``)::

      const firstTier = feeTiers[0];
      if (marketCap.lt(firstTier.marketCapLamportsThreshold)) return firstTier.fees;
      for (const tier of feeTiers.slice().reverse())
        if (marketCap.gte(tier.marketCapLamportsThreshold)) return tier.fees;
      return firstTier.fees;

  i.e. **the highest threshold that is ``<=`` the market cap wins** (the boundary
  belongs to the upper tier), and a market cap below the first threshold takes the
  first tier. :func:`fees_for_market_cap` is that function, integer-exact.
- market cap of a bonding curve (same file, ``bondingCurveMarketCap``):
  ``virtualSolReserves * mintSupply / virtualTokenReserves`` — see
  :func:`bonding_curve_market_cap_lamports`.

**What the live account says (2026-09-16, slot 447 586 137,**
``tests/fixtures/pumpfun/rpc_fee_config_raw.json``**)**: the config of the *bonding
curve* program has a **single** tier, threshold 0, ``lp 0 / protocol 95 / creator
30`` — 1,25 %, exactly the dated constant, and **independent of the market cap**.
The 25-tier table of ``docs/fees.png`` lives in the PumpSwap config
(``t429c_rpc_fee_config_amm_raw.json``), for pools, not for curves. So today the
constant is right; this module is what will notice the day it stops being.
"""

from __future__ import annotations

import base64
import struct
from dataclasses import dataclass

from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.quote import BONDING_CURVE_FEE_TIER_2026_05_20, FeeBps
from hunter_exchanges.pumpfun.solana_codec import b58encode, find_program_address, pubkey_bytes

__all__ = [
    "FEE_CONFIG_DISCRIMINATOR",
    "FEE_CONFIG_UNAVAILABLE_EVENT",
    "FEE_CONFIG_SEED",
    "FEE_PROGRAM_ID",
    "PUMP_SWAP_PROGRAM_ID",
    "FeeConfig",
    "FeeTier",
    "Fees",
    "bonding_curve_market_cap_lamports",
    "curve_fee_bps",
    "decode_fee_config",
    "fee_config_address",
    "fees_for_market_cap",
]

#: Pump Fees — owner of ``FeeConfig``; account index 13 of every ``sell`` since 12/09.
FEE_PROGRAM_ID = "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ"
#: PumpSwap (Pump AMM) — its own ``FeeConfig``, the tiered one (pools, not curves).
PUMP_SWAP_PROGRAM_ID = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
FEE_CONFIG_SEED = b"fee_config"
FEE_CONFIG_DISCRIMINATOR = bytes.fromhex("8f3492bbdb7b4c9b")

_BPS = 10_000
_FEES_LEN = 24
_U128_LEN = 16
_TIER_LEN = _U128_LEN + _FEES_LEN
_HEADER_LEN = len(FEE_CONFIG_DISCRIMINATOR) + 1 + 32 + _FEES_LEN  # disc, bump, admin, flat_fees


@dataclass(frozen=True, slots=True)
class Fees:
    """``Fees`` of the IDL: three ``u64`` basis points. ``lp_fee_bps`` is always 0 on a
    bonding curve (there is no LP) and is kept because the account carries it."""

    lp_fee_bps: int
    protocol_fee_bps: int
    creator_fee_bps: int

    def __post_init__(self) -> None:
        values = (self.lp_fee_bps, self.protocol_fee_bps, self.creator_fee_bps)
        if any(isinstance(v, bool) or v < 0 for v in values) or sum(values) >= _BPS:
            raise ValueError("fee basis points must be >= 0 and sum below 10_000")

    @property
    def total_bps(self) -> int:
        return self.lp_fee_bps + self.protocol_fee_bps + self.creator_fee_bps


@dataclass(frozen=True, slots=True)
class FeeTier:
    """``FeeTier``: ``market_cap_lamports_threshold: u128`` + ``fees: Fees``."""

    market_cap_lamports_threshold: int
    fees: Fees


@dataclass(frozen=True, slots=True)
class FeeConfig:
    """The decoded account. ``decoded_length``/``trailing_bytes`` describe how much of
    the (over-allocated, zero-padded) account the layout above actually explains —
    the live curve config is 4 097 bytes of which 177 are fields."""

    bump: int
    admin: str
    flat_fees: Fees
    fee_tiers: tuple[FeeTier, ...]
    stable_fee_tiers: tuple[FeeTier, ...]
    exotic_flat_fees: Fees | None
    decoded_length: int
    trailing_bytes: int


def fee_config_address(config_program_id: str = PUMP_PROGRAM_ID) -> str:
    """PDA ``["fee_config", config_program_id]`` **under the fee program** — the seeds
    the IDL declares for the ``fee_config`` account of ``buy``/``sell``/``get_fees``."""
    address, _bump = find_program_address(
        [FEE_CONFIG_SEED, pubkey_bytes(config_program_id)], FEE_PROGRAM_ID
    )
    return address


class _Cursor:
    def __init__(self, raw: bytes) -> None:
        self.raw = raw
        self.off = len(FEE_CONFIG_DISCRIMINATOR)

    def need(self, size: int) -> None:
        if self.off + size > len(self.raw):
            raise MalformedMessage(
                f"FeeConfig is truncated: need {size} bytes at offset {self.off} "
                f"of {len(self.raw)}",
                exchange="pumpfun",
            )

    def u8(self) -> int:
        self.need(1)
        value = self.raw[self.off]
        self.off += 1
        return value

    def u32(self) -> int:
        self.need(4)
        (value,) = struct.unpack_from("<I", self.raw, self.off)
        self.off += 4
        return value

    def pubkey(self) -> str:
        self.need(32)
        value = b58encode(self.raw[self.off : self.off + 32])
        self.off += 32
        return value

    def fees(self) -> Fees:
        self.need(_FEES_LEN)
        lp, protocol, creator = struct.unpack_from("<QQQ", self.raw, self.off)
        self.off += _FEES_LEN
        return Fees(lp_fee_bps=lp, protocol_fee_bps=protocol, creator_fee_bps=creator)

    def tiers(self) -> tuple[FeeTier, ...]:
        count = self.u32()
        self.need(count * _TIER_LEN)  # refuse an absurd length prefix before allocating
        out: list[FeeTier] = []
        for _ in range(count):
            threshold = int.from_bytes(self.raw[self.off : self.off + _U128_LEN], "little")
            self.off += _U128_LEN
            out.append(FeeTier(market_cap_lamports_threshold=threshold, fees=self.fees()))
        return tuple(out)


def decode_fee_config(data_base64: str | bytes, *, owner: str) -> FeeConfig:
    """Decode a ``getAccountInfo`` payload of ``FeeConfig``.

    Refuses a foreign owner, a wrong discriminator, a truncated body or a tier
    vector longer than the account instead of guessing (D1). ``exotic_flat_fees``
    is optional: accounts written before that field existed end after
    ``stable_fee_tiers`` and decode with ``None``.
    """
    if owner != FEE_PROGRAM_ID:
        raise MalformedMessage(
            f"FeeConfig owner {owner!r} is not the pump.fun fee program", exchange="pumpfun"
        )
    if isinstance(data_base64, bytes):
        raw = data_base64
    else:
        try:
            raw = base64.b64decode(data_base64, validate=True)
        except (ValueError, TypeError) as exc:
            raise MalformedMessage(
                f"FeeConfig data is not base64: {exc}", exchange="pumpfun"
            ) from exc
    if len(raw) < _HEADER_LEN:
        raise MalformedMessage(f"FeeConfig is truncated: {len(raw)} bytes", exchange="pumpfun")
    if raw[: len(FEE_CONFIG_DISCRIMINATOR)] != FEE_CONFIG_DISCRIMINATOR:
        raise MalformedMessage("wrong FeeConfig discriminator", exchange="pumpfun")
    cursor = _Cursor(raw)
    try:
        bump = cursor.u8()
        admin = cursor.pubkey()
        flat_fees = cursor.fees()
        fee_tiers = cursor.tiers()
        stable_fee_tiers = cursor.tiers()
        exotic = cursor.fees() if cursor.off + _FEES_LEN <= len(raw) else None
    except ValueError as exc:  # a bad bool/bps inside an otherwise well-formed account
        raise MalformedMessage(f"FeeConfig field is invalid: {exc}", exchange="pumpfun") from exc
    return FeeConfig(
        bump=bump,
        admin=admin,
        flat_fees=flat_fees,
        fee_tiers=fee_tiers,
        stable_fee_tiers=stable_fee_tiers,
        exotic_flat_fees=exotic,
        decoded_length=cursor.off,
        trailing_bytes=len(raw) - cursor.off,
    )


def fees_for_market_cap(
    config: FeeConfig, market_cap_lamports: int, *, stable: bool = False
) -> Fees:
    """``pump-fees-math::calculate_fee_tier`` — see the module docstring for the source.

    The highest threshold ``<=`` the market cap wins; a market cap below the first
    threshold takes the first tier. ``stable=True`` selects ``stable_fee_tiers``
    (quote mints the program treats as stable); the bonding curve path uses
    ``fee_tiers``.
    """
    if isinstance(market_cap_lamports, bool) or market_cap_lamports < 0:
        raise ValueError("market cap must be a non-negative integer of lamports")
    tiers = config.stable_fee_tiers if stable else config.fee_tiers
    if not tiers:
        raise ValueError("fee_tiers is empty: the account carries no schedule to apply")
    first = tiers[0]
    if market_cap_lamports < first.market_cap_lamports_threshold:
        return first.fees
    for tier in reversed(tiers):
        if market_cap_lamports >= tier.market_cap_lamports_threshold:
            return tier.fees
    return first.fees


def bonding_curve_market_cap_lamports(
    *, mint_supply: int, virtual_sol_reserves: int, virtual_token_reserves: int
) -> int:
    """``virtualSolReserves * mintSupply / virtualTokenReserves`` (floor), the
    ``bondingCurveMarketCap`` of the fee program README.

    ``mint_supply`` is the **mint's** supply (``getTokenSupply``).
    ``BondingCurve.token_total_supply`` is the usual proxy and equals it while
    nothing has been burned — pass whichever the caller can prove, never both.
    """
    if virtual_token_reserves <= 0:
        raise ValueError("virtual token reserves must be positive")
    if mint_supply < 0 or virtual_sol_reserves < 0:
        raise ValueError("supply and reserves are non-negative integers")
    return virtual_sol_reserves * mint_supply // virtual_token_reserves


FEE_CONFIG_UNAVAILABLE_EVENT = "meme_fee_config_unavailable"
"""What a caller logs when it could not read the ``FeeConfig`` account and fell
back to the constant above — the one event that says "these fees are dated"."""


def curve_fee_bps(
    config: FeeConfig | None, *, market_cap_lamports: int, floor: FeeBps | None = None
) -> tuple[FeeBps, str]:
    """The bonding-curve fee set, from the chain when we have it (T4.29c).

    ``config`` is the decoded ``FeeConfig`` of the **pump program**
    (``decode_fee_config``); ``None`` means the account could not be
    read — then :data:`quote.BONDING_CURVE_FEE_TIER_2026_05_20` is returned and the
    second element of the tuple is :data:`FEE_CONFIG_UNAVAILABLE_EVENT`, which the
    caller is expected to log. With a config the tier is selected by market cap
    (``fees_for_market_cap``) and the source is ``"fee_config"``.

    ``floor`` (optional) is applied component-wise with ``max`` — the executor
    floors the creator share so a stale read can never *under*-estimate a cost.
    A tier that charges an ``lp_fee_bps`` on a curve is refused instead of being
    silently dropped: a curve has no LP, so that would mean the schedule changed
    shape and every quote would be too cheap.
    """
    if config is None:
        fees = BONDING_CURVE_FEE_TIER_2026_05_20
        source = FEE_CONFIG_UNAVAILABLE_EVENT
    else:
        tier = fees_for_market_cap(config, market_cap_lamports)
        if tier.lp_fee_bps:
            raise ValueError(
                f"fee_config tier charges lp_fee_bps={tier.lp_fee_bps} on a bonding curve"
            )
        fees = FeeBps(protocol=tier.protocol_fee_bps, creator=tier.creator_fee_bps)
        source = "fee_config"
    if floor is not None:
        fees = FeeBps(
            protocol=max(fees.protocol, floor.protocol), creator=max(fees.creator, floor.creator)
        )
    return fees, source
