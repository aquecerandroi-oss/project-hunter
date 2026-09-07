"""The three numbers that bound the collector's proof of continuity.

Extracted from :mod:`hunter_market_worker.coverage` (T3.0c) for the 350-line
budget, and along a real seam: these are the *policy* of the proof — how far
short of the clock it stops, how often it is restated, and how long it stays
believable without being restated — while ``coverage.py`` is the machinery that
decides what may be claimed. ``coverage.py`` re-exports all three, so no
importer changes.
"""

from __future__ import annotations

COVERAGE_SAFETY_S = 0.5
"""How far short of the clock a stamp stops. Covers the adapter's own inbound
queue, which this process cannot inspect: an event received 100 ms ago may not
have been yielded to the ingest loop yet, and claiming it as tape would be
exactly the fabricated coverage that module exists to avoid."""

COVERAGE_STAMP_S = 0.25
"""Cadence of the stamp. Bounds how far behind the scanner's cut runs, and with
it the tick->opportunity latency the cut is measured against (p99 <= 3 s)."""

COVERAGE_TTL_S = 60
"""A dead collector's proof must expire on its own: a scanner that kept reading
a stale hash would keep publishing windows nobody is collecting."""

__all__ = ["COVERAGE_SAFETY_S", "COVERAGE_STAMP_S", "COVERAGE_TTL_S"]
