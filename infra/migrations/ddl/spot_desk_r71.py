"""``0061_spot_desk_r71`` — the six markets R71 added to ``spot_desk_markets``.

**Why.** The ``spot/1`` desk only ever looks at markets that are in the map
(``spot_repo._CANDIDATES`` joins ``spot_desk_markets ... AND d.enabled``), and
R71 (23/09/2026, ``.claude/state/notes-R71.md``) measured how much of the Lab's
``mean_reversion`` output the map was missing: of the **68** Binance symbols the
family signalled in 14 days and the map did not cover, only **six** have a
Solana token that survives R63's filter — price parity with Binance inside
+-3 %, a route, and a round trip under 1 %. The other 62, ``DASHUSDT`` (121
signals in 14 days, the largest single hole) and ``PROMUSDT`` among them, have
**no validated representation on Solana**: their homonyms in Jupiter's open
search are unverified memecoins quoting 100 % away from Binance — R63 §2's
54 false homonyms, again.

**The rule is ``0057``'s, unchanged**: ``enabled`` at seed is
:func:`ddl.spot_desk_seed.is_enabled_at_seed` — ``tier <> 'C' AND round trip
<= 0,4 %`` — so no criterion was loosened to make this list longer. Two rows it
would have enabled are held back **by name** in :data:`HELD_FOR_REVIEW_0061`,
for a risk that rule never looked at (see the constant); holding a row back is
not loosening anything, and the operator's audited
``infra/scripts/spot_desk_markets.py --enable`` is one command away.

**Identity — the failure this revision exists to prevent.** A wrong mint means
the desk buys the wrong token with real money. Every mint below was proved
twice, at the same instant, against the Binance mark (R63 §2's filter, never
the ``verified`` tag alone), and then reviewed by Astra
(``.claude/state/astra-review-r71.md``), who closed the identity of the two
bridged ones at their source:

- ``NEARUSDT`` -> NEAR **OmniBridge** (``omni.bridge.near``):
  ``get_token_id('sol:3ZLek...')`` answers ``wrap.near`` and
  ``get_token_address('Sol', 'wrap.near')`` answers the same mint, both ways;
  the mint authority is the ``authority`` PDA of the official
  ``bridge_token_factory`` program.
- ``XRPUSDT`` -> **Hex Trust**'s wXRP, the mint published on
  ``hextrust.com/services/wrapping/wxrp``.
- ``BTCUSDT`` -> **WBTC (Portal)**, in Wormhole's own token list against
  Ethereum's ``0x2260fac5...``; its mint authority is the Wormhole token
  bridge PDA that also signs the ``ETH``/``SPX``/``AUDIO``/``BNB`` rows
  ``0057`` already planted.
- ``BIRBUSDT``, ``SLXUSDT``, ``ORCAUSDT`` are the same mints R63 §2 had already
  measured, re-measured here.

Percentages are a **fraction** (``0.003125`` = 0,3125 %), DATABASE.md §1, as in
``ddl/spot_desk_seed.py``; liquidity is the US$ Jupiter reported at 19:35 UTC;
the round trip is the 0,05 SOL leg (the desk's size) of 19:40-19:44 UTC.
``decimals`` stays ``NULL``: the executor reads the mint once and writes it
back, exactly as for ``0057``'s fifty.

The insert is ``ON CONFLICT (binance_symbol) DO NOTHING`` and the downgrade
removes **only these six**, and refuses first if a ``spot_orders`` or a
``spot_positions`` row names one of them (§17.7) — a real Jupiter transaction
would lose the market its ledger points at.
"""

from __future__ import annotations

from decimal import Decimal

import sqlalchemy as sa
from alembic import op

from ddl.spot_desk_seed import SpotDeskMarketSeed, is_enabled_at_seed

SEED_WRITER_0061 = "migration:0061_spot_desk_r71"
"""``updated_by`` of every row this revision plants — the operator's script
writes its own, which is how the downgrade and the tests tell them apart."""

# (binance_symbol, mint, kind, tier, liquidity_usd, round_trip_cost at 0,05 SOL)
# Ordered by the `mean_reversion` signals of the last 14 days, most first.
# fmt: off
SPOT_DESK_SEED_0061: tuple[tuple[str, str, str, str, int, str], ...] = (
    ("NEARUSDT", "3ZLekZYq2qkZiSpnSvabjit34tUkjSwD1JFuW9as9wBG", "ponte", "A", 1955016, "0.001442"),
    ("XRPUSDT", "6UpQcMAb5xMzxc7ZfPaVMgx3KqsvKZdT5U718BzD5We2", "ponte", "A", 1025805, "0.003125"),
    ("BIRBUSDT", "G7vQWurMkMMm2dU3iZpXYFTHT9Biio4F4gZCrwFpKNwG", "nativo", "A", 1262831, "0.000123"),
    ("SLXUSDT", "SLXdx4BUt2v9uJQNzWqSfzTJ9UKLUDsvxHFMEEdrfgq", "nativo", "C", 93126, "0.000728"),
    ("BTCUSDT", "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh", "ponte", "A", 39144617, "0.000036"),
    ("ORCAUSDT", "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE", "nativo", "B", 343934, "0.001096"),
)
# fmt: on
"""R71's measurement. Every market is 1:1 with its Binance unit (no ``1000``
prefix among them), so ``units_per_binance_unit`` is not carried per row."""

HELD_FOR_REVIEW_0061: dict[str, str] = {
    "XRPUSDT": (
        "a freeze authority ativa do custodiante (Hex Trust) pode congelar a conta de token: "
        "o stop da mesa deixaria de ser executavel com a posicao aberta"
    ),
    "BIRBUSDT": (
        "90,9 % do supply nos maiores detentores, sem decomposicao entre pools, custodia e "
        "vesting: uma venda concentrada esvazia a liquidez antes do stop"
    ),
}
"""Two rows the ``0057`` rule would enable and R71 holds back by name, each for
a risk the rule never looked at (Astra, revisao r71, must-fix 2 e 3). This is a
**restricao adicional**, nunca um afrouxamento: nenhum ``tier`` ou custo foi
mexido para produzir o ``false``. Everton reverte cada uma com um comando do
``infra/scripts/spot_desk_markets.py --enable``."""

_NOTES: dict[str, str] = {
    "NEARUSDT": (
        "R71 23/09/2026: wNEAR da NEAR OmniBridge (omni.bridge.near responde wrap.near para este "
        "mint, nos dois sentidos; mint authority = PDA authority do bridge_token_factory oficial). "
        "Paridade com a Binance +0,44 % (oraculo) e -0,02 %/+0,20 % (preco executavel de 0,05 SOL, "
        "duas amostras). Ida-e-volta 0,074 % / 0,144 % / 0,126 % em 0,02 / 0,05 / 0,2 SOL."
    ),
    "XRPUSDT": (
        "R71 23/09/2026: wXRP da Hex Trust (mint publicado em hextrust.com/services/wrapping/wxrp). "
        "Paridade +0,34 % (oraculo), +0,38 %/+0,44 % (executavel). Ida-e-volta 0,311 % / 0,312 % / "
        "0,324 %. DESABILITADO na semente apesar de passar na regra: a freeze authority do "
        "custodiante continua ativa e uma conta congelada nao vende."
    ),
    "BIRBUSDT": (
        "R71 23/09/2026: mesmo mint do R63 §2 (Moonbirds), mint e freeze revogadas. Paridade "
        "-0,14 % (oraculo), -0,15 %/-0,08 % (executavel). Ida-e-volta 0,009 % / 0,012 % / 0,027 %. "
        "DESABILITADO na semente: 90,9 % do supply nos maiores detentores, sem decomposicao."
    ),
    "SLXUSDT": (
        "R71 23/09/2026: mesmo mint do R63 §2 (Solstice, solstice.finance), mint e freeze "
        "revogadas. Paridade -0,77 % (oraculo), -0,34 %/-0,25 % (executavel). Ida-e-volta "
        "-0,046 % / 0,073 % / 0,111 %. Desabilitado pela regra: tier C (93 k US$ de liquidez)."
    ),
    "BTCUSDT": (
        "R71 23/09/2026: WBTC (Portal), na lista oficial da Wormhole contra o WBTC da Ethereum "
        "(0x2260fac5...); mesma mint authority do ETH/SPX/AUDIO/BNB da 0057. Paridade -0,04 % "
        "(oraculo), -0,01 %/-0,02 % (executavel). Ida-e-volta 0,011 % / 0,004 % / 0,004 %. "
        "Risco declarado: duas camadas (lastro do WBTC e ponte Portal)."
    ),
    "ORCAUSDT": (
        "R71 23/09/2026: mesmo mint do R63 §2 (Orca, publicado na governanca do projeto), freeze "
        "revogada e mint authority ainda ativa. Paridade -0,29 % (oraculo), +0,15 %/+0,36 % "
        "(executavel). Ida-e-volta 0,055 % / 0,110 % / 0,188 %."
    ),
}
"""``note`` of each row: where the identity came from, what was measured and —
when it is off — why. The column is what an operator reads before enabling."""

SPOT_DESK_R71_INSERT = sa.text(
    "INSERT INTO spot_desk_markets (binance_symbol, base, mint, units_per_binance_unit, kind, "
    "  tier, liquidity_usd_at_seed, round_trip_cost_pct_at_seed, enabled, note, updated_by) "
    "VALUES (:binance_symbol, :base, :mint, :units_per_binance_unit, :kind, :tier, "
    "  :liquidity_usd_at_seed, :round_trip_cost_pct_at_seed, :enabled, :note, :updated_by) "
    "ON CONFLICT (binance_symbol) DO NOTHING"
)


def seed_note(binance_symbol: str) -> str:
    """The ``note`` R71 writes for ``binance_symbol``."""
    return _NOTES[binance_symbol]


def seed_rows_0061() -> tuple[SpotDeskMarketSeed, ...]:
    """The six rows, with ``enabled`` = ``0057``'s rule AND not held back."""
    rows: list[SpotDeskMarketSeed] = []
    for symbol, mint, kind, tier, liquidity, cost in SPOT_DESK_SEED_0061:
        round_trip = Decimal(cost)
        rows.append(
            SpotDeskMarketSeed(
                binance_symbol=symbol,
                base=symbol.removesuffix("USDT"),
                mint=mint,
                units_per_binance_unit=1,
                kind=kind,
                tier=tier,
                liquidity_usd_at_seed=liquidity,
                round_trip_cost_pct_at_seed=round_trip,
                enabled=is_enabled_at_seed(tier, round_trip) and symbol not in HELD_FOR_REVIEW_0061,
            )
        )
    return tuple(rows)


def seed_parameters() -> list[dict[str, object]]:
    """The bound parameters of :data:`SPOT_DESK_R71_INSERT` — no interpolation
    anywhere near a mint or a note."""
    return [
        {**row._asdict(), "note": seed_note(row.binance_symbol), "updated_by": SEED_WRITER_0061}
        for row in seed_rows_0061()
    ]


def seed_spot_desk_markets_r71() -> None:
    """Idempotent: a row an operator already edited is never overwritten."""
    op.get_bind().execute(SPOT_DESK_R71_INSERT, seed_parameters())


def unseed_spot_desk_markets_r71() -> None:
    """Removes exactly the six symbols this revision added — ``0057``'s fifty
    are not named here and are not touched."""
    op.get_bind().execute(
        sa.text("DELETE FROM spot_desk_markets WHERE binance_symbol IN :symbols").bindparams(
            sa.bindparam("symbols", expanding=True)
        ),
        {"symbols": [symbol for symbol, *_ in SPOT_DESK_SEED_0061]},
    )


_GUARDED: tuple[tuple[str, str], ...] = (
    (
        "spot_orders",
        "orders name a market this revision added - removing the row loses the map entry its "
        "mint, its tier and its measured cost were read from",
    ),
    (
        "spot_positions",
        "positions name a market this revision added - a position is money on the chain and the "
        "market it points at cannot leave under it",
    ),
)


def refuse_a_downgrade_that_would_orphan_a_spot_row() -> None:
    """§17.7: reversing is allowed, losing a ledger's market is not — lock,
    count, name, stop.

    The lock comes first (``ddl/spot_desk.py``'s reasoning): counting and then
    deleting leaves a window in which the executor admits an order on one of
    these markets between the two. The foreign keys would refuse the ``DELETE``
    anyway; this turns that into a message that says which table and why.
    """
    op.execute("LOCK TABLE spot_orders, spot_positions IN ACCESS EXCLUSIVE MODE")
    symbols = ", ".join(f"'{symbol}'" for symbol, *_ in SPOT_DESK_SEED_0061)
    for table, why in _GUARDED:
        predicate = f"WHERE market_symbol IN ({symbols})"
        safe_predicate = predicate.replace("'", "''")
        safe_why = why.replace("'", "''")
        op.execute(
            f"DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608 - this module's own constants
            f"SELECT count(*) INTO offenders FROM {table} {predicate}; "
            f"IF offenders > 0 THEN RAISE EXCEPTION USING "
            f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {table} rows exist - {safe_why}', "
            f"HINT = 'COPY (SELECT * FROM {table} {safe_predicate}) TO ... before reversing'; "
            f"END IF; END $$;"
        )


__all__ = [
    "HELD_FOR_REVIEW_0061",
    "SEED_WRITER_0061",
    "SPOT_DESK_R71_INSERT",
    "SPOT_DESK_SEED_0061",
    "refuse_a_downgrade_that_would_orphan_a_spot_row",
    "seed_note",
    "seed_parameters",
    "seed_rows_0061",
    "seed_spot_desk_markets_r71",
    "unseed_spot_desk_markets_r71",
]
