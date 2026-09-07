"""The BRL side of the wallet: the opening conversion and the BRL attribution.

Pure arithmetic — no session, no clock, no I/O. Two operations live here because
they are the same boundary: BRL is what the directive names (R$100.000) and USDT
is what the engine operates in, and every crossing of that boundary has to be
reconstructible years later from numbers that were written down once.

**The attribution, and why the currency term sits on the patrimony.** With ``E``
the equity in USDT, ``E0`` the capital actually credited and ``F0``/``Ft`` the
opening and current BRL-per-USDT rates:

```
operacional_brl = (E − E0) · F0
cambial_brl     = E · (Ft − F0)
equity_brl      = E · Ft = E0·F0 + operacional_brl + cambial_brl
```

Astra's arithmetic check of 2026-09-06 (``.claude/state/dialogue-M3.md``, round
1) measured what the other reading costs: with **cash** in the currency term
instead of the patrimony, a wallet with equity 20.200, cash 12.000, F0 = 5 and
Ft = 6 loses **R$8.200** of the identity. Cash is a part of the patrimony; the
rate moves all of it, including the part that is currently sitting in a
position. The convention — attributing the operating result at the *opening*
rate — is declared, not universal, and the screen says so.

**The opening conversion, and why the residue is written down.**
``portfolio_currency_anchor`` proves the money identity with a CHECK,
``round(credited·rate + residual, 10) = round(origin, 10)`` (DATABASE.md §18.2),
and Postgres rounds ``numeric`` halves *away from zero*. Since ``credited`` and
``rate`` each hold ten decimals, their product holds twenty and the residue
column holds ten, so the residue is the exact difference **rounded to the stored
scale** — and the policy has to pick the rounding that keeps the CHECK true.
:data:`OPENING_ROUNDING_POLICY` is that whole algorithm, named and versioned:

1. ``credited = floor10(origin / rate)`` — the wallet never receives more than
   was converted, and the floor is taken on the exact rational quotient
   (integer division of the scaled coefficients), never on a quotient that a
   ``Decimal`` context already rounded;
2. ``residual`` is ``floor10`` of the exact remainder, or ``ceil10`` when the
   discarded fraction is more than half a quantum — the tie going to the floor
   (Astra, T3.3 policy review, must-fix 1: with ``origin = 100000`` and
   ``rate = 3.5`` the remainder is ``2,5e-10`` and only the floor keeps the
   CHECK true). One of the two always works, because the two candidates land at
   ``origin − ε`` and ``origin + (q − ε)`` with ``0 ≤ ε < q``.

The stored residue is therefore within half a quantum (5e-11 BRL) of the exact
one, in either direction, and never negative.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext

from pydantic import BaseModel, ConfigDict

ORIGIN_CURRENCY = "BRL"
"""The currency the directive is written in: "Começar com R$100.000 fictícios"."""

OPERATING_CURRENCY = "USDT"
"""``portfolios.base_currency``. "Não confundir R$100.000 com 100.000 USDT"."""

FX_PAIR = "USDTBRL"
"""``fx_observations.pair``: BRL per USDT, which is the direction ``rate`` has."""

OPENING_ROUNDING_POLICY = "floor_10dp_v1"
"""Written to ``portfolio_currency_anchor.rounding_policy``. Versioned because
changing it changes the number a wallet started from — and that number is
``E0``, which every BRL attribution is measured against."""

SCALE = 10
"""``NUMERIC(28,10)``: the stored scale of every money column (DATABASE.md §1)."""

QUANTUM = Decimal(1).scaleb(-SCALE)
"""One unit of the last stored decimal place."""

LEDGER_CONTEXT = Context(prec=50, rounding=ROUND_HALF_EVEN)
"""Wider than ``hunter_core.strategies.numeric.CONTEXT`` (28 digits) on purpose.

The attribution multiplies a ten-decimal equity by a ten-decimal rate, so a
six-figure wallet already needs 27 significant digits and a seven-figure one
needs 28 — exactly where the strategy context starts rounding, and a rounded
product breaks the identity ``E0·F0 + operacional + cambial = E·Ft`` by an
amount nobody can explain. Fifty digits is far beyond what these products need;
the arithmetic here is exact, and the only rounding in this module is the
declared one in :func:`convert_opening`.
"""

_SCALE_FACTOR = 10**SCALE


class OpeningConversion(BaseModel):
    """What :func:`convert_opening` decided, in the shape the anchor stores."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    origin_amount: Decimal
    rate: Decimal
    credited_amount: Decimal
    conversion_residual: Decimal
    rounding_policy: str = OPENING_ROUNDING_POLICY


class BrlAttribution(BaseModel):
    """The wallet in BRL, with the operating result kept apart from the rate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    equity: Decimal
    """``E`` — total patrimony in the operating currency."""

    credited: Decimal
    """``E0`` — what the wallet was actually credited at the opening."""

    opening_rate: Decimal
    """``F0`` — the anchored rate, from the observation the wallet opened on."""

    current_rate: Decimal
    """``Ft`` — the rate of the observation this reading names."""

    opening_brl: Decimal
    """``E0 · F0``: the capital as it was, in BRL. Not ``origin_amount``: the
    residue the conversion could not credit is not part of the patrimony."""

    operational_brl: Decimal
    """``(E − E0) · F0`` — the result of the operations, at the opening rate."""

    currency_brl: Decimal
    """``E · (Ft − F0)`` — the rate's effect on the **whole** patrimony."""

    equity_brl: Decimal
    """``E · Ft``."""

    total_brl: Decimal
    """``E·Ft − E0·F0`` — the two terms above, which is the identity itself."""


def _scaled(value: Decimal) -> int:
    """``value`` as an integer number of quanta. Exact for a stored ``NUMERIC``."""
    with localcontext(LEDGER_CONTEXT):
        shifted = value.scaleb(SCALE)
    integral = shifted.to_integral_value()
    if integral != shifted:
        raise ValueError(
            f"{value} has more than {SCALE} decimal places and cannot be stored in "
            "NUMERIC(28,10) without silently losing money"
        )
    return int(integral)


def convert_opening(origin_amount: Decimal, rate: Decimal) -> OpeningConversion:
    """Convert ``origin_amount`` BRL at ``rate`` under :data:`OPENING_ROUNDING_POLICY`.

    Returns the credit and the residue the anchor stores. Raises ``ValueError``
    when the inputs are not money the schema accepts, or when the rate is so
    large that the wallet would be credited nothing — a wallet that opens at
    zero is not an opening, and failing here is the honest outcome.
    """
    if origin_amount <= 0:
        raise ValueError(f"origin_amount must be positive, got {origin_amount}")
    if rate <= 0:
        raise ValueError(f"rate must be positive, got {rate}")

    origin_units = _scaled(origin_amount)
    rate_units = _scaled(rate)

    # floor(origin / rate) at the stored scale, on the exact rational quotient.
    credited_units = (origin_units * _SCALE_FACTOR) // rate_units
    if credited_units <= 0:
        raise ValueError(
            f"a rate of {rate} credits nothing for {origin_amount} {ORIGIN_CURRENCY} at "
            f"{SCALE} decimal places; the wallet would open at zero"
        )

    # The exact remainder, in units of 1e-20 (a ten-decimal credit times a
    # ten-decimal rate), split into whole quanta and a discarded fraction.
    remainder_fine = origin_units * _SCALE_FACTOR - credited_units * rate_units
    residual_units, fraction = divmod(remainder_fine, _SCALE_FACTOR)
    if 2 * fraction > _SCALE_FACTOR:
        residual_units += 1

    with localcontext(LEDGER_CONTEXT):
        credited = Decimal(credited_units).scaleb(-SCALE)
        residual = Decimal(residual_units).scaleb(-SCALE)
    return OpeningConversion(
        origin_amount=origin_amount,
        rate=rate,
        credited_amount=credited,
        conversion_residual=residual,
    )


def attribute_brl(
    *, equity: Decimal, credited: Decimal, opening_rate: Decimal, current_rate: Decimal
) -> BrlAttribution:
    """Split the wallet's BRL result into operating and currency terms.

    ``equity`` is the **whole patrimony** in the operating currency: cash plus
    every open position marked to market, costs included. Passing cash instead
    is the error the module docstring prices at R$8.200.
    """
    if opening_rate <= 0 or current_rate <= 0:
        raise ValueError(
            f"an FX rate must be positive, got opening_rate={opening_rate} "
            f"and current_rate={current_rate}"
        )
    with localcontext(LEDGER_CONTEXT):
        opening_brl = credited * opening_rate
        operational_brl = (equity - credited) * opening_rate
        currency_brl = equity * (current_rate - opening_rate)
        equity_brl = equity * current_rate
        total_brl = equity_brl - opening_brl
    return BrlAttribution(
        equity=equity,
        credited=credited,
        opening_rate=opening_rate,
        current_rate=current_rate,
        opening_brl=opening_brl,
        operational_brl=operational_brl,
        currency_brl=currency_brl,
        equity_brl=equity_brl,
        total_brl=total_brl,
    )
