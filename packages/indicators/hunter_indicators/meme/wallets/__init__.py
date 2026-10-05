"""H-030 — the pure engine of "follow wallets that make real money" (wave 1c).

Design: ``docs/design/seguir-carteiras-lucrativas.md``; pre-registration:
``.claude/state/carteiras-lucro/PREREG.md``. No IO and no clock read anywhere in
the package: every instant comes from an event or from the caller.

- :mod:`.tape` — the decoded event (:class:`~.tape.Fill`), identity/dedupe and
  :func:`~.tape.causal_view` (mined **and** received before an instant);
- :mod:`.lots` — FIFO lots, realized PnL net of fees (W-PnL), unmatched sales;
- :mod:`.pricing` — the §3.1 price contract (last state ≤ slot, worst of the
  landing slot, real-SOL ceiling always on, migration without pool → censored);
- :mod:`.episodes` — episodes and the E-PnL (cash + Δ liquidation value);
- :mod:`.entities` — union-find entities, versioned by ``known_at``;
- :mod:`.metrics` — eligibility and the historical exclusions;
- :mod:`.policy` — the copy simulation, shared by C-PnL and the arms;
- :mod:`.follow` — `follow`/`control` as pure ``evaluate`` + the H2 pairing;
- :mod:`.ranking` / :mod:`.snapshot` — the daily snapshot and the one in force;
- :mod:`.leakage` — the perturbation leak test and the snapshot-read audit.
"""

from __future__ import annotations
