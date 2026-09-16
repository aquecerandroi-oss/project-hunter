"""PumpSwap (Pump AMM) — read-only pool/config decode, a pure sell quote, and a
``sell`` instruction builder. **Sell only** (T4.29a): this project never buys on
PumpSwap (``docs/RISK_ENGINE_MEME.md`` §1 — PumpSwap is only the exit door for a
position whose coin migrated). Nothing here signs or sends a transaction.

See ``docs/PUMPFUN.md`` §"PumpSwap (venda pós-migração)" and
``.claude/state/notes-T4.29a.md`` for the IDL source, its sha256, and the
mainnet reads this package's constants and formulas were checked against.
"""

from __future__ import annotations
