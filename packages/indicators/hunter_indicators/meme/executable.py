"""Executable value on a Mayhem curve (T4.27): the market cap and the mark
never claim more SOL than the curve actually holds.

**The fact.** Measured on the VPS (3 days to 16/09/2026,
``infra/scripts/sql/research/2026-09-16-t427-picos-sao-mayhem.sql``): every
one of the 95 "peaks" of theoretical market cap above 500 SOL was a Mayhem
coin, 76 of them with less than 20 % of the curve sold. KAT's
``virtual_sol_reserves`` went 23,9 → 1 977 SOL in 60 s with 5 holders and
``real_token_reserves`` down 7 %: the agent (``set_mayhem_virtual_params``,
``docs/PUMPFUN-ONCHAIN.md`` §1.3) pushed the *virtual* reserve; nobody paid
SOL in. ``mcap_sol`` (marginal price × supply, ``T4-MEME-RADAR.md`` §4) read
1 981 SOL "of market cap" that no seller could take out.

**The rule.** ``real_sol_reserves`` — the SOL in the curve's vault — is the
ceiling of what can leave it. So:

- :func:`executable_market_cap_sol` — ``mcap_executable_sol``: the theoretical
  market cap **capped at the real SOL** for a Mayhem coin; identical to the
  theoretical one for a standard coin (its virtual reserve above the launch
  value *is* the real SOL, ``PUMPFUN-ONCHAIN.md`` §1.2: a buy raises both by
  the same lamports). Not a price — a ceiling on what every holder together
  could extract; written beside ``mcap_sol`` on both feature series (``0042``);
- :func:`sell_cap_sol` — the ceiling a position's mark uses
  (:func:`~hunter_indicators.meme.curve.sell_all_value_sol`): the real SOL of
  the photo for a coin still on the curve unless it is known standard (where
  the ceiling cannot bind anyway); ``None`` for a **completed** curve, whose
  SOL has left for the pool and whose executable value is the pool's tape
  (T4.11);
- :func:`is_mayhem_curve` — one answer from the two things the rows carry:
  the chain's ``is_mayhem_mode`` bit (``mayhem_enabled``) and the site's
  agent state, which only a Mayhem coin has (``active``/``paused``/
  ``completed``). ``None`` = not observed; ``unknown`` is a label the site
  emitted and we could not map, not evidence of an agent.

Registered as a feature (key, version, params, description, inputs); the
formula changing is a new version, never an edit.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

from hunter_core.domain.enums import FeatureCategory
from hunter_indicators.features.definitions import FeatureDefinition

__all__ = [
    "EXECUTABLE_DEFINITIONS",
    "MAYHEM_AGENT_STATES",
    "executable_market_cap_sol",
    "is_mayhem_curve",
    "sell_cap_sol",
]

MAYHEM_AGENT_STATES: Final = frozenset({"active", "paused", "completed"})
"""The site's agent states (``meme_tokens.mayhem_state``); only a Mayhem coin
has one. ``unknown`` is excluded on purpose (``mayhem_labels.py``)."""

EXECUTABLE_DEFINITIONS: Final[tuple[FeatureDefinition, ...]] = (
    FeatureDefinition(
        key="mcap_executable_sol",
        version=1,
        category=FeatureCategory.PRICE,
        inputs=(
            "meme_curve_snapshots.mcap_sol",
            "meme_curve_snapshots.real_sol_reserves",
            "meme_curve_snapshots.mayhem_enabled",
            "meme_tokens.mayhem_enabled",
            "meme_tokens.mayhem_state",
        ),
        description=(
            "Theoretical market cap (marginal price x supply, SOL) capped at the curve's "
            "real SOL reserve for a Mayhem coin; equal to mcap_sol for a standard coin. "
            "A ceiling on what every holder could extract, not a price."
        ),
        params={"cap": "real_sol_reserves", "applies_to": "mayhem"},
    ),
)


def is_mayhem_curve(mayhem_enabled: bool | None, mayhem_state: str | None = None) -> bool | None:
    """The chain's bit when read; else the site's agent state, which only a
    Mayhem coin has; else ``None`` — not observed, never "not Mayhem"."""
    if mayhem_enabled is not None:
        return mayhem_enabled
    if mayhem_state in MAYHEM_AGENT_STATES:
        return True
    return None


def executable_market_cap_sol(
    mcap_sol: Decimal | None, real_sol_reserves: Decimal | None, *, mayhem: bool | None
) -> Decimal | None:
    """``min(mcap_sol, real_sol_reserves)`` for a Mayhem coin, ``mcap_sol``
    otherwise (a standard coin's theoretical cap is already backed by real
    SOL). ``None`` exactly when ``mcap_sol`` is — and, for a Mayhem coin,
    when the photo did not carry its real SOL: a cap nobody observed is not
    a cap of zero."""
    if mcap_sol is None:
        return None
    if not mayhem:
        return mcap_sol
    if real_sol_reserves is None:
        return None
    return min(mcap_sol, real_sol_reserves)


def sell_cap_sol(
    real_sol_reserves: Decimal | None, *, mayhem: bool | None, complete: bool
) -> Decimal | None:
    """The ceiling of a position's mark: the photo's real SOL for a coin still
    on the curve unless it is **known** standard; ``None`` (no ceiling) for a
    standard coin and for a completed curve (its SOL is on the pool now).

    An unknown flag keeps the ceiling: on a standard curve it cannot bind (the
    vault is what the buyers paid), so the conservative reading costs a
    standard coin nothing and protects the mark of a Mayhem coin the chain
    has not yet been asked about.
    """
    if mayhem is False or complete:
        return None
    return real_sol_reserves
