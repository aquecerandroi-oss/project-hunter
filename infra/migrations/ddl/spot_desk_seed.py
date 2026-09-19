"""The seed of ``spot_desk_markets`` (``0057_spot_desk``, T4.74-1): the 50
Binance markets the Lab monitors that are executable on Solana through
Jupiter — R63 §2a (``.claude/state/notes-R63.md``, 2026-09-19 13:10–13:12
UTC, round trip of 0,05 SOL), minus ``SOLUSDT`` (buying SOL with SOL is not a
position) and ``ENAUSDT`` (1,02 % round trip — the only one of the 52 above
1 %).

**Every mint below is copied from the R63 JSON map (§6) and cross-checked
against the §2a table by the script that generated these rows — never typed
from memory.** ``1000BONKUSDT``/``1000PEPEUSDT`` are 1 000 tokens per Binance
unit; every other market is 1:1.

``enabled`` is not stored here: it is *derived* by :func:`seed_rows` from the
rule the design fixes (``docs/design/spot1-lab-solana.md`` §2) —
``tier <> 'C' AND round_trip_cost <= 0,4 %`` — so the rule lives in one
place and the table can be re-read against it. Tier C (liquidity below
100 k US$, R63 §5.5) and a round trip above 0,4 % are both left to the
operator's ``infra/scripts/spot_desk_markets.py --enable``.

Percentages are stored as a **fraction** (``0.00193`` = 0,193 %), DATABASE.md
§1; the 0,4 % rule is therefore ``<= 0.004``. Liquidity is US$ as R63 read it
from Jupiter, an integer.
"""

from __future__ import annotations

from decimal import Decimal
from typing import NamedTuple

SEED_WRITER_0057 = "migration:0057_spot_desk"
"""``updated_by`` of every seeded row — the operator's script writes its own."""

ENABLE_MAX_ROUND_TRIP_COST_0057 = Decimal("0.004")
"""The 0,4 % round-trip ceiling of the enable rule, as a fraction."""

ENABLE_EXCLUDED_TIER_0057 = "C"

# (binance_symbol, mint, units_per_binance_unit, kind, tier, liquidity_usd, round_trip_cost)
# fmt: off
SPOT_DESK_SEED_0057: tuple[tuple[str, str, int, str, str, int, str], ...] = (
    ("ETHUSDT", "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs", 1, "ponte", "A", 23113927, "-0.00004"),
    ("ZECUSDT", "A7bdiYdS5GjqGFtxf17ppRHtDKPkkRqbKtR27dxvQXaS", 1, "nativo", "A", 5852605, "0.0005"),
    ("HYPEUSDT", "98sMhvDwXj1RQi5c5Mndm3vPe9cBqPrbLaufMXFNMh5g", 1, "nativo", "A", 5637051, "-0.00005"),
    ("UNIUSDT", "uniHfuPhEQSrtpzXpJZDCSq53yaejKKpNhFUiKoHKHV", 1, "representacao", "B", 310102, "0.00193"),
    ("BNBUSDT", "9gP2kCy3wA1ctvYWQk75guqXuHfrEomqydHLtcTCqiLa", 1, "ponte", "B", 198037, "0.00254"),
    ("DOGEUSDT", "DoGEV7LASBkQbibMc5k5vKnTZoMg423GpJ5QtJEGfm7R", 1, "representacao", "B", 658314, "0.0014"),
    ("SUIUSDT", "suifhC9gU1VbJAPYPTBkHJyyyStKGLLYPVDTmPoqbvA", 1, "representacao", "C", 74790, "0.00198"),
    ("AVAXUSDT", "avaxGHCq3T7hoxd73oY2KY9hJSTaeMibXvHy5KNzh5D", 1, "representacao", "C", 62513, "0.00398"),
    ("ARBUSDT", "ARBzQTYDCW2KnVEjs1Mc81LekB1ibVFZKbSVmorkoT9d", 1, "representacao", "B", 242283, "0.00372"),
    ("1000PEPEUSDT", "PEPEqnuuCDbBC89p1u9vpnP1KQ2oj1xTcQBsjt9X55m", 1000, "representacao", "B", 682888, "0.00342"),
    ("TAOUSDT", "taoC6xyv2v8tDLcev4uaGUgV4vdQsWJrGft2kcBRrBY", 1, "nativo", "B", 525855, "0.00236"),
    ("LINKUSDT", "LinkhB3afbBKb2EQQu7s7umdZceV3wcvAUJhQAfQ23L", 1, "representacao", "B", 194255, "0.00319"),
    ("STRKUSDT", "HsRpHQn6VbyMs5b5j5SV6xQ2VvpvvCCzu19GjytVSCoz", 1, "representacao", "C", 49227, "0.00486"),
    ("AAVEUSDT", "AavE1kKKnesPw4MuRJmJ9jZs9QzEE8CPxQ3ViczUDfc1", 1, "representacao", "B", 108344, "0.00135"),
    ("XMRUSDT", "WXMRyRZhsa19ety5erZhHg4N3xj3EVN92u94422teJp", 1, "nativo", "B", 706659, "0.00153"),
    ("PUMPUSDT", "pumpCmXqMfrsAkQ5r49WcJnRayYRqmXz6ae8H7H9Dfn", 1, "nativo", "A", 37048689, "0.00035"),
    ("INJUSDT", "1NJMqVM4PadjuzYmeB7zV7q7DV8oB3ExaQCd9x6KsLz", 1, "representacao", "B", 294770, "0.00251"),
    ("TRUMPUSDT", "6p6xgHyF7AeE6TZkSmFsko444wqoP15icUSqi2jfGiPN", 1, "nativo", "A", 33303910, "0.00051"),
    ("PONSUSDT", "poNSfquKq512ApeYjVghwViSun4x1MhCqHVH2Paq4jN", 1, "nativo", "B", 132548, "0.00021"),
    ("LITUSDT", "EicWvteVi2fWepEzS3FYWsnuPoP6caZfjnKqNvydLjCH", 1, "nativo", "B", 611445, "0.00135"),
    ("USELESSUSDT", "Dz9mQ9NzkBcCsuGPFJ3r1bS4wgqKMHBPiVuniW8Mbonk", 1, "nativo", "A", 4163905, "0.00109"),
    ("PENGUUSDT", "2zMMhcVQEXDtdE6vsFS7S7D5oUodfJHE8vd1gnBouauv", 1, "nativo", "A", 2462435, "0.00005"),
    ("TRXUSDT", "GbbesPbaYh5uiAZSYNXTc7w9jty1rpg3P9L4JeN4LkKc", 1, "nativo", "A", 4528222, "-0.00012"),
    ("JUPUSDT", "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", 1, "nativo", "A", 4894798, "0.00027"),
    ("FARTCOINUSDT", "9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump", 1, "nativo", "A", 6230340, "0.00047"),
    ("WIFUSDT", "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", 1, "nativo", "A", 6475681, "0.00082"),
    ("1000BONKUSDT", "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", 1000, "nativo", "A", 1396700, "-0.00003"),
    ("JTOUSDT", "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL", 1, "nativo", "B", 330199, "0.0001"),
    ("VIRTUALUSDT", "3iQL8BFS2vE7mww4ehAqQHAsbmRNCrPxizWAT2Zfyr9y", 1, "nativo", "A", 1965238, "0.00601"),
    ("RENDERUSDT", "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof", 1, "nativo", "B", 215119, "0.00095"),
    ("CHIPUSDT", "chipCAT7vi5CZtbZsn9z7iMPXvFwyAnKz3QFu8XVuHm", 1, "representacao", "B", 100035, "0.00025"),
    ("CAKEUSDT", "4qQeZ5LwSz6HuupUu8jCtgXyW1mYQcNbFAW1sWZp89HL", 1, "representacao", "C", 61979, "0.00038"),
    ("WLFIUSDT", "WLFinEv6ypjkczcS83FZqFpgFZYwQXutRbxGe7oC16g", 1, "nativo", "C", 37937, "0.00593"),
    ("MONUSDT", "CrAr4RRJMBVwRsZtT62pEhfA9H5utymC2mVx8e7FreP2", 1, "nativo", "B", 156608, "0.00027"),
    ("GALAUSDT", "eEUiUs4JWYZrp72djAGF1A8PhpR6rHphGeGN7GbVLp6", 1, "representacao", "C", 11748, "0.00539"),
    ("METUSDT", "METvsvVRapdj9cFLzq4Tr43xK4tAjQfwX76z3n6mWQL", 1, "nativo", "A", 3966654, "0.00039"),
    ("BOMEUSDT", "ukHH6c7mMyiWCf1b9pnWe25TSpkDDt3H5pQZgZ74J82", 1, "nativo", "A", 17073819, "0.00088"),
    ("DRIFTUSDT", "DriFtupJYLTosbwoN8koMbEYSx54aFAVLddWsbksjwg7", 1, "nativo", "C", 68014, "0.00185"),
    ("PYTHUSDT", "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3", 1, "nativo", "B", 409809, "0.00101"),
    ("WUSDT", "85VBFQZC9TZkfaptBWjvUw7YbZjy52A6mjtPGjstQAmQ", 1, "nativo", "B", 125757, "0.00007"),
    ("SPXUSDT", "J3NKxxXZcnNiMjKw9hYb2K4LUxgwB6t1FtPtQVsv3KFr", 1, "ponte", "A", 3063768, "0.00389"),
    ("ARXUSDT", "ARXwZkNAtzPfdcoqQiduJn8EPv9fKiDfGn2KyggyDrFs", 1, "nativo", "B", 470012, "0.00458"),
    ("MEGAUSDT", "megaA5QDK1qLXtjpvg9oCFMvxT9d5BCMrVTBddnM5kV", 1, "representacao", "C", 42123, "0.00486"),
    ("CHZUSDT", "6eftxVbSAunVEoxUWdGhPdxg5UdsJ8Wkwy5w5YFuxouw", 1, "representacao", "C", 45128, "0.00491"),
    ("SKRUSDT", "SKRbvo6Gf7GondiT3BbTfuRDPqLWei4j2Qy2NPGZhW3", 1, "nativo", "B", 710757, "0.00125"),
    ("PNUTUSDT", "2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump", 1, "nativo", "A", 3570015, "0.005"),
    ("MOODENGUSDT", "ED5nyyWEzpPPiWimP8vYm7sD7TD3LAt3Q3gRTWHzPJBY", 1, "nativo", "A", 1467197, "0.005"),
    ("BIOUSDT", "bioJ9JTqW62MLz7UKHU69gtKhPpGi1BQhccj2kmSvUJ", 1, "nativo", "B", 160696, "0.00149"),
    ("CHILLGUYUSDT", "Df6yfrKC8kZE3KNkrHERKzAetSxbrWeniQfyJY4Jpump", 1, "nativo", "B", 835488, "0.00501"),
    ("GRASSUSDT", "Grass7B4RdKfBCjTKgSqnXkqjwiGvQyFbuSCUJr3XXjs", 1, "nativo", "C", 55789, "0.00592"),
)
# fmt: on
"""R63 §2a in table order (Binance rank), ``SOLUSDT`` and ``ENAUSDT`` removed."""


class SpotDeskMarketSeed(NamedTuple):
    """One row of ``spot_desk_markets`` as the migration inserts it."""

    binance_symbol: str
    base: str
    mint: str
    units_per_binance_unit: int
    kind: str
    tier: str
    liquidity_usd_at_seed: int
    round_trip_cost_pct_at_seed: Decimal
    enabled: bool


def is_enabled_at_seed(tier: str, round_trip_cost: Decimal) -> bool:
    """The design's rule (§2): ``tier <> 'C' AND round trip <= 0,4 %``."""
    return tier != ENABLE_EXCLUDED_TIER_0057 and round_trip_cost <= ENABLE_MAX_ROUND_TRIP_COST_0057


def seed_rows() -> tuple[SpotDeskMarketSeed, ...]:
    """The 50 rows with ``base`` derived (``1000PEPEUSDT`` -> ``1000PEPE``, as
    R63 names it) and ``enabled`` derived from the rule above."""
    rows: list[SpotDeskMarketSeed] = []
    for symbol, mint, units, kind, tier, liquidity, cost in SPOT_DESK_SEED_0057:
        round_trip = Decimal(cost)
        rows.append(
            SpotDeskMarketSeed(
                binance_symbol=symbol,
                base=symbol.removesuffix("USDT"),
                mint=mint,
                units_per_binance_unit=units,
                kind=kind,
                tier=tier,
                liquidity_usd_at_seed=liquidity,
                round_trip_cost_pct_at_seed=round_trip,
                enabled=is_enabled_at_seed(tier, round_trip),
            )
        )
    return tuple(rows)


__all__ = [
    "ENABLE_EXCLUDED_TIER_0057",
    "ENABLE_MAX_ROUND_TRIP_COST_0057",
    "SEED_WRITER_0057",
    "SPOT_DESK_SEED_0057",
    "SpotDeskMarketSeed",
    "is_enabled_at_seed",
    "seed_rows",
]
