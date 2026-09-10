"""``ShadowConfig.claim_idle_ms``'s default and the arithmetic behind it.

Split out of ``config.py`` (T3.82) purely for that file's own 350-line budget
-- this is derivation logic for one field, not a knob itself; ``config.py``
re-exports every name here unchanged, so nothing importing them from there
needs to change.
"""

from __future__ import annotations

__all__ = ["CLAIM_IDLE_MS_CEILING", "EXPECTED_BAR_COST_S", "default_claim_idle_ms"]

EXPECTED_BAR_COST_S: float = 8.0
"""Conservative worst-case wall time of one ``handle_candle`` call under load,
grounding :data:`ShadowConfig.claim_idle_ms`'s default -- not a guess.

``docs/DEPLOYMENT.md``'s "Custo medido" measured ~1.4-1.5 evaluations/s per
*due version* on this shape of workload (T3.74b). A bar can have up to 11
versions of one family due at once (T3.74's roster) and ``handle_candle``'s
per-version loop is sequential by design -- the T3.74b family cache shares the
candle *read* across versions, never the ``evaluate_slot``/persist call, which
still pays its own DB round trips per version. 11 / 1.4 ~= 7.9s, rounded up.
"""


CLAIM_IDLE_MS_CEILING: int = 90_000
"""Hard ceiling on :func:`default_claim_idle_ms`'s output (T3.74e).

The naive product (``worker_concurrency x EXPECTED_BAR_COST_S``) was sized
when ``worker_concurrency`` was 8 and assumed a bar queued behind a full
dispatcher waits for at most *one round* of already-running bars -- true only
when the burst is shallow. T3.74e measured the real burst depth instead: the
whole monitored universe (~200 perpetuals) shares every 15m/30m/1h boundary,
so at ``worker_concurrency`` raised to absorb that (32, this module's new
default) the naive product is 32 x 8.0 x 1000 = 256 000 ms -- 85 % of
``consumer_stall_s``'s 300 000 ms default, violating the "well under" bound
``ShadowConfig.claim_idle_ms`` documents (``test_claim_idle_ms.py``). The
realistic worst wait at that concurrency, measured live (``notes-T3.74e.md``
§1), is an order of magnitude smaller (~10 s for a 200-market burst); 90 000 ms
keeps an 8x+ safety margin over that measurement while staying at 30 % of the
stall bound, comfortably under the "less than half" the existing test already
enforces.
"""


def default_claim_idle_ms(worker_concurrency: int) -> int:
    """Default for :data:`ShadowConfig.claim_idle_ms`: ``worker_concurrency ×
    EXPECTED_BAR_COST_S``, in milliseconds (T3.74d), capped at
    :data:`CLAIM_IDLE_MS_CEILING` (T3.74e -- see that constant's docstring for
    why the uncapped product stops being a meaningful bound once
    ``worker_concurrency`` is sized for a universe-wide burst).

    See ``ShadowConfig.claim_idle_ms``'s own docstring for the review finding
    this answers and the bound it must respect.
    """
    return min(int(max(1, worker_concurrency) * EXPECTED_BAR_COST_S * 1000), CLAIM_IDLE_MS_CEILING)
