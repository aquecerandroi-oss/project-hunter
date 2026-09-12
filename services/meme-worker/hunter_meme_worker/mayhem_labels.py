"""The site's mayhem labels, held to the schema's CHECKs (12/09/2026, 16:4x BRT).

After the holder-rewards upgrade of 12/09 the REST API started emitting
``mayhem_state = "enabled"`` (seen on ``25xPUKHq…`` minutes after creation; the
same coin answered ``paused`` a few minutes later). ``meme_tokens`` and
``meme_curve_snapshots`` refuse that label (``ck_…_mayhem_state_is_a_known_label``:
``active``, ``paused``, ``completed``, ``unknown``), the poll loop died on the
CHECK, the process restarted and every other loop died with it (RestartCount 1,
four tracebacks in six minutes, deploy 1033999). An unknown label becomes
``unknown`` **here**, at the one boundary between the adapter's state and the
rows (``curve_rows.py``), logged once per (field, mint, label) with the raw
value so a plantão can name it later — never a crash, never a silent drop.
"""

from __future__ import annotations

from hunter_core.logging import get_logger

logger = get_logger(__name__)

KNOWN_MAYHEM_STATES: frozenset[str] = frozenset({"active", "paused", "completed", "unknown"})
KNOWN_MAYHEM_MODES: frozenset[str] = frozenset({"auto", "manual", "unknown"})
UNKNOWN = "unknown"
_SEEN_CAP = 10_000
_seen: set[tuple[str, str, str]] = set()


def known_mayhem_state(raw: str | None, *, mint: str, source: str) -> str | None:
    """``raw`` when the schema knows it, ``None`` when absent, else ``unknown`` (logged)."""
    return _known(raw, KNOWN_MAYHEM_STATES, field="mayhem_state", mint=mint, source=source)


def known_mayhem_mode(raw: str | None, *, mint: str, source: str) -> str | None:
    """Same rule for ``mayhem_mode`` (``auto``/``manual``/``unknown``)."""
    return _known(raw, KNOWN_MAYHEM_MODES, field="mayhem_mode", mint=mint, source=source)


def _known(
    raw: str | None, known: frozenset[str], *, field: str, mint: str, source: str
) -> str | None:
    if raw is None or raw in known:
        return raw
    key = (field, mint, raw)
    if key not in _seen:
        if len(_seen) >= _SEEN_CAP:
            _seen.clear()
        _seen.add(key)
        logger.warning(
            "meme_mayhem_label_unknown", field=field, label=raw, mint=mint, source=source
        )
    return UNKNOWN
