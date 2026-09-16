"""The two pump.fun bonding-curve PDAs, split out of ``tx.py`` (T4.39).

``normalize.py`` needs :func:`bonding_curve_address` to check a PumpPortal
``create`` frame's ``bondingCurveKey`` against the address the program itself
would derive — a comparison the trade-instruction builder has nothing to do
with, so it lives here instead of pulling ``tx.py`` (and its ``GlobalAccount``/
``solana_codec`` instruction-building dependencies) into the ingest boundary.
``tx.py`` re-exports both names so every existing import
(``from hunter_exchanges.pumpfun.tx import bonding_curve_address``) keeps
working unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence

from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.solana_codec import find_program_address, pubkey_bytes

__all__ = ["bonding_curve_address", "bonding_curve_v2_address"]


def _pda(seeds: Sequence[bytes], program: str = PUMP_PROGRAM_ID) -> str:
    return find_program_address(seeds, program)[0]


def bonding_curve_address(mint: str) -> str:
    return _pda([b"bonding-curve", pubkey_bytes(mint)])


def bonding_curve_v2_address(mint: str) -> str:
    """The remaining account the 2026-09-12 program validates (6074) — derived, never typed."""
    return _pda([b"bonding-curve-v2", pubkey_bytes(mint)])
