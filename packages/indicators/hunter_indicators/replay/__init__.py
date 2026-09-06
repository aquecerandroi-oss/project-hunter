"""R1 — replay of exit policies over the Lab's frozen entries (EXP-0004).

Pure half of the experiment: the eight exit policies as *declarations*, the
predicates they evaluate at a bar close, the paired contrasts with their
time-block resampling and Holm correction, and the Lab's named metrics.

Nothing here reads a database, a clock or a candle table. Binding a policy to
the real tracking code (``hunter_strategy_worker.walker`` / ``.settle``) is the
job of ``hunter_strategy_worker.replay``: the replay reuses the production
walker and never reimplements the exit rules.
"""

from __future__ import annotations
