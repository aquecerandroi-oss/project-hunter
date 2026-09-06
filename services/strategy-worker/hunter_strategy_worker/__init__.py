"""hunter_strategy_worker — the Shadow Lab worker (``HUNTER_ROLE=strategy``).

Consumes ``market.candles.closed``, evaluates the activated ``strategy_version``
rows on their own timeframe closes, persists each decision with its immutable
envelope, and follows the hypothetical outcome bar by bar. It is the single
writer of Shadow Lab outcomes (docs/plans/SHADOW-LAB.md §10).

It never places an order, never sizes a position and never touches a portfolio:
every signal carries ``purpose = research_only`` and travels on its own stream.
The agent runner, proposal builder and risk gate described for this role in
``docs/ARCHITECTURE.md`` §7 arrive in M4.
"""

__version__ = "0.0.0"
