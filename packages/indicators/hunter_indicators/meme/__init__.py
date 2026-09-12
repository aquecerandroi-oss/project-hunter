"""T4.5 — the pure paper simulator of the pump.fun bonding curve.

Four modules, no IO and no clock read anywhere in the package:

- :mod:`hunter_indicators.meme.curve` — the trade arithmetic of a constant
  product curve (``virtual_sol * virtual_token = k``), the fee as a
  **parameter**, and the reserves *after our own trade* (our impact);
- :mod:`hunter_indicators.meme.paper` — :class:`~.paper.PaperCurveWallet`, a
  SOL-capped paper wallet whose fills are always priced against reserves
  observed **after** the intent, never against the last seen price;
- :mod:`hunter_indicators.meme.rules` — the entry gate and the exit rules as
  pure functions, every refusal and every exit named;
- :mod:`hunter_indicators.meme.replay` — one mint's snapshot series run through
  the wallet, producing the Lab's outcome shape (entry, exit, reason, R in SOL,
  holding time) so EXP-M1 can be read with day-block CIs.

The boundary with ``hunter_exchanges.pumpfun``: that package owns the wire
format (WS/REST/RPC decoding, lamports, subunits, ``NormalizedCurveState``) and
this one owns the arithmetic of a trade. The two share the price/mcap formulas
and the live-confirmed constants; the parity is asserted by
``packages/indicators/tests/unit/test_meme_curve.py`` instead of imported,
because ``hunter-indicators`` does not depend on ``hunter-exchanges`` and adding
that edge for two constants would invert the layering for nothing.
"""

from __future__ import annotations
