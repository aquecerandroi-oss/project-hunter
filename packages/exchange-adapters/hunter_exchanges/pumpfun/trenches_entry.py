"""One wire entry of ``/ws/trenches`` (short keys) -> :class:`NormalizedBoardEntry`.

The only module that reads the two-letter keys of the board protocol
(``docs/PUMPFUN.md`` §3.1, measured live on 2026-09-12): every other layer sees
the long names of ``board_models.py``. Split from ``trenches_state.py`` for the
350-line budget — the *state* of a board is there, the *reading* of one entry is
here.

Coercions are refusals, not guesses: an integer key holding a boolean, a number
key holding text, a negative epoch — each is :class:`MalformedMessage`, and the
whole message is skipped and counted by the client. A key this module does not
know goes to ``extra`` raw and labelled. Percent keys (``t10``, ``dh``) become
fractions once, here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.pumpfun.board_models import TRENCHES_SOURCE, NormalizedBoardEntry

EXCHANGE = "pumpfun"

_INT_KEYS = {
    "tx5": "tx_5m",
    "age": "age_s",
    "kol": "kol_count",
    "sn": "snipers",
    "bc": "buys",
    "sc": "sells",
    "txc": "txs",
    "nh": "holders",
    "np": "participants",
}
_DECIMAL_KEYS = {
    "mc": "market_cap_usd",
    "p": "progress_pct",
    "v": "volume_sol",
    "vUsd": "volume_usd",
    "v5": "volume_5m_sol",
    "v15": "volume_15m_sol",
    "v1h": "volume_1h_sol",
    "v24h": "volume_24h_sol",
    "vUsd5": "volume_5m_usd",
    "vUsd15": "volume_15m_usd",
    "vUsd1h": "volume_1h_usd",
    "vUsd24h": "volume_24h_usd",
    "ath": "ath_market_cap_usd",
    "tf": "fees_sol",
    "tfUsd": "fees_usd",
}
_PERCENT_KEYS = {"t10": "top10_share", "dh": "dev_share"}
_BOOL_KEYS = {
    "mh": "is_mayhem",
    "hs": "has_social",
    "tw": "has_twitter",
    "ws": "has_website",
    "tg": "has_telegram",
    "cb": "cashback",
    "lv": "is_live",
}
_TEXT_KEYS = {
    "c": "chain",
    "n": "name",
    "t": "symbol",
    "i": "image_uri",
    "pg": "program",
    "pl": "platform",
    "pa": "quote_asset",
    "dw": "dev_wallet",
    "desc": "description",
    "ms": "mayhem_state",
}
_EPOCH_MS_KEYS = {"gd": "graduated_at"}
_HUNDRED = Decimal(100)


def malformed(text: str) -> MalformedMessage:
    return MalformedMessage(f"trenches {text}", exchange=EXCHANGE)


def _int(value: Any, key: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise malformed(f"field {key!r} is a boolean, not an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    raise malformed(f"field {key!r} is not an integer: {value!r}")


def _decimal(value: Any, key: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise malformed(f"field {key!r} is not a number: {value!r}")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise malformed(f"field {key!r} is not decimal: {value!r}") from exc
    if not result.is_finite():
        raise malformed(f"field {key!r} is not finite: {value!r}")
    return result


def _bool(value: Any, key: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise malformed(f"field {key!r} is not a boolean: {value!r}")
    return value


def _text(value: Any, key: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise malformed(f"field {key!r} is not text: {value!r}")
    return value or None


def _epoch_ms(value: Any, key: str) -> datetime | None:
    ms = _int(value, key)
    if ms is None or ms == 0:
        return None
    if ms < 0:
        raise malformed(f"field {key!r} is a negative instant")
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def _percent_to_fraction(value: Any, key: str) -> Decimal | None:
    number = _decimal(value, key)
    return None if number is None else number / _HUNDRED


def parse_entry(
    raw: dict[str, Any],
    *,
    board: str,
    position: int,
    version: int,
    observed_at: datetime,
    received_at: datetime,
    source: str = TRENCHES_SOURCE,
) -> NormalizedBoardEntry:
    """One wire entry (short keys) -> :class:`NormalizedBoardEntry`."""
    mint = raw.get("m")
    if not isinstance(mint, str) or not mint:
        raise malformed("entry has no mint")
    fields: dict[str, Any] = {}
    extra: dict[str, Any] = {}
    for key, value in raw.items():
        if key == "m":
            continue
        if key in _INT_KEYS:
            fields[_INT_KEYS[key]] = _int(value, key)
        elif key in _DECIMAL_KEYS:
            fields[_DECIMAL_KEYS[key]] = _decimal(value, key)
        elif key in _PERCENT_KEYS:
            fields[_PERCENT_KEYS[key]] = _percent_to_fraction(value, key)
        elif key in _BOOL_KEYS:
            fields[_BOOL_KEYS[key]] = _bool(value, key)
        elif key in _TEXT_KEYS:
            fields[_TEXT_KEYS[key]] = _text(value, key)
        elif key in _EPOCH_MS_KEYS:
            fields[_EPOCH_MS_KEYS[key]] = _epoch_ms(value, key)
        else:
            extra[key] = str(value) if isinstance(value, Decimal) else value
    return NormalizedBoardEntry(
        board=board,
        position=position,
        version=version,
        mint=mint,
        observed_at=observed_at,
        received_at=received_at,
        extra=extra,
        source=source,
        **fields,
    )


__all__ = ["EXCHANGE", "malformed", "parse_entry"]
