"""One stable hash slice, shared by every sharded worker (T3.74f).

``hunter_market_worker.universe.shard_symbols`` proved this shape first
(T1.6b-C2): ``zlib.crc32`` over the UTF-8 bytes of a symbol, never Python's
built-in ``hash()`` (salted per-process by ``PYTHONHASHSEED`` -- two workers,
or even two runs of the same worker, would not agree with themselves, let
alone with each other). The strategy-worker's own sharding (T3.74f) needs a
symbol to land on the *same* shard index the market-worker already uses it
for elsewhere in the pipeline, so the one function moved here instead of
being re-derived a second time with the same formula and a chance to drift.
"""

from __future__ import annotations

import zlib

__all__ = ["crc32_shard", "owns", "parse_shard_spec"]


def parse_shard_spec(field_name: str, value: str) -> tuple[int, int]:
    """``"<index>/<total>"`` -> ``(index, total)``, validated (T1.6b-C1).

    Fails loudly and immediately -- a worker that silently fell back to "the
    whole universe" on a typo'd shard variable would duplicate every other
    shard's load instead of refusing to start. Shared by
    ``Settings.market_shard`` and ``Settings.strategy_shard`` (T3.74f) --
    same shape, same failure mode, one place to get the message right.
    ``field_name`` is only used in the error message (e.g. ``"MARKET_SHARD"``).
    """
    parts = value.split("/")
    if len(parts) != 2:
        raise ValueError(f"{field_name} must be '<index>/<total>', got {value!r}")
    try:
        index, total = int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise ValueError(
            f"{field_name} must be '<index>/<total>' with integers, got {value!r}"
        ) from exc
    if total < 1:
        raise ValueError(f"{field_name} total must be >= 1, got {value!r}")
    if not (0 <= index < total):
        raise ValueError(f"{field_name} index must satisfy 0 <= index < total, got {value!r}")
    return index, total


def crc32_shard(key: str, shard_total: int) -> int:
    """Stable shard index for ``key`` in ``[0, shard_total)``.

    UTF-8, not ASCII: Binance USDS-M lists perpetuals whose symbol is written
    in Chinese (``牛来USDT`` was rank 19 by 24h volume on 2026-09-05) --
    encoding as ASCII would raise ``UnicodeEncodeError`` instead of sharding.
    """
    return zlib.crc32(key.encode("utf-8")) % shard_total


def owns(key: str, shard_index: int, shard_total: int) -> bool:
    """Whether shard ``shard_index`` of ``shard_total`` owns ``key``."""
    return crc32_shard(key, shard_total) == shard_index
