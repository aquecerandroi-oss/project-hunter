"""Every write and read of the T4.2c sources — as ``hunter_worker``, never as owner.

Same discipline as ``repo.py``: each function takes an ``AsyncSession`` opened by
``role_session(..., db_role="hunter_worker")``, nothing here opens a transaction,
and idempotence is a fact of the schema rather than of a prior read:

- a board minute is ``ON CONFLICT (observed_at, board, mint) DO NOTHING``;
- a trade is ``ON CONFLICT (block_time, signature, event_index) DO NOTHING`` —
  the dedupe the brief asks for, by the key ``0021`` chose (MUST-FIX 2);
- a risk read is ``ON CONFLICT (observed_at, mint) DO NOTHING``.

The tape half (``TradeRow``, ``trade_rows``, ``insert_trades``, ``load_tape``,
``open_bet_mints``) lives in ``repo_tape.py`` and is re-exported here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.db.meme_risk_snapshots import RISK_COLUMNS, insert_risk_snapshot
from hunter_meme_worker.repo_rows import clean_text
from hunter_meme_worker.repo_tape import (
    TradeRow,
    insert_trades,
    load_tape,
    open_bet_mints,
    trade_rows,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_exchanges.pumpfun.board_models import NormalizedBoardEntry


@dataclass(frozen=True, slots=True)
class BoardMinuteRow:
    """One row of ``meme_board_observations``."""

    observed_at: datetime
    board: str
    mint: str
    minute_end: datetime
    received_at: datetime
    mint_updated_at: datetime | None
    version: int
    position: int
    patches: int
    first_seen_in_board_at: datetime
    last_seen_in_board_at: datetime
    left_board_at: datetime | None
    exposure_censored: bool
    source: str
    chain: str | None = None
    program: str | None = None
    platform: str | None = None
    quote_asset: str | None = None
    name: str | None = None
    symbol: str | None = None
    market_cap_usd: Decimal | None = None
    progress_pct: Decimal | None = None
    volume_sol: Decimal | None = None
    volume_usd: Decimal | None = None
    volume_5m_sol: Decimal | None = None
    volume_15m_sol: Decimal | None = None
    volume_1h_sol: Decimal | None = None
    volume_24h_sol: Decimal | None = None
    volume_5m_usd: Decimal | None = None
    volume_15m_usd: Decimal | None = None
    volume_1h_usd: Decimal | None = None
    volume_24h_usd: Decimal | None = None
    tx_5m: int | None = None
    age_s: int | None = None
    kol_count: int | None = None
    snipers: int | None = None
    is_mayhem: bool | None = None
    mayhem_state: str | None = None
    has_social: bool | None = None
    has_twitter: bool | None = None
    has_website: bool | None = None
    has_telegram: bool | None = None
    graduated_at: datetime | None = None
    ath_market_cap_usd: Decimal | None = None
    buys: int | None = None
    sells: int | None = None
    txs: int | None = None
    holders: int | None = None
    top10_share: Decimal | None = None
    dev_share: Decimal | None = None
    cashback: bool | None = None
    dev_wallet: str | None = None
    is_live: bool | None = None
    participants: int | None = None
    fees_sol: Decimal | None = None
    fees_usd: Decimal | None = None
    extra: dict[str, Any] | None = None


_ENTRY_COLUMNS = (
    "chain",
    "program",
    "platform",
    "quote_asset",
    "name",
    "symbol",
    "market_cap_usd",
    "progress_pct",
    "volume_sol",
    "volume_usd",
    "volume_5m_sol",
    "volume_15m_sol",
    "volume_1h_sol",
    "volume_24h_sol",
    "volume_5m_usd",
    "volume_15m_usd",
    "volume_1h_usd",
    "volume_24h_usd",
    "tx_5m",
    "age_s",
    "kol_count",
    "snipers",
    "is_mayhem",
    "mayhem_state",
    "has_social",
    "has_twitter",
    "has_website",
    "has_telegram",
    "graduated_at",
    "ath_market_cap_usd",
    "buys",
    "sells",
    "txs",
    "holders",
    "top10_share",
    "dev_share",
    "cashback",
    "dev_wallet",
    "is_live",
    "participants",
    "fees_sol",
    "fees_usd",
)


def board_minute_row(
    entry: NormalizedBoardEntry,
    *,
    minute_end: datetime,
    observed_at: datetime,
    received_at: datetime,
    patches: int,
    position: int,
    first_seen_in_board_at: datetime,
    last_seen_in_board_at: datetime,
    left_board_at: datetime | None,
    exposure_censored: bool,
) -> BoardMinuteRow:
    """The last version of an entry seen in a minute, plus the exposure interval."""
    values = {column: getattr(entry, column) for column in _ENTRY_COLUMNS}
    return BoardMinuteRow(
        observed_at=observed_at,
        board=entry.board,
        mint=entry.mint,
        minute_end=minute_end,
        received_at=received_at,
        mint_updated_at=entry.observed_at,
        version=entry.version,
        position=position,
        patches=patches,
        first_seen_in_board_at=first_seen_in_board_at,
        last_seen_in_board_at=last_seen_in_board_at,
        left_board_at=left_board_at,
        exposure_censored=exposure_censored,
        source=entry.source,
        extra=entry.extra or None,
        **values,
    )


_BOARD_COLUMNS = (
    "observed_at",
    "board",
    "mint",
    "minute_end",
    "received_at",
    "mint_updated_at",
    "version",
    "position",
    "patches",
    "first_seen_in_board_at",
    "last_seen_in_board_at",
    "left_board_at",
    "exposure_censored",
    "source",
    *_ENTRY_COLUMNS,
)

_INSERT_BOARD_MINUTE = text(
    f"INSERT INTO meme_board_observations ({', '.join(_BOARD_COLUMNS)}, extra) "  # noqa: S608
    f"VALUES ({', '.join(':' + column for column in _BOARD_COLUMNS)}, "
    "COALESCE(CAST(:extra AS jsonb), '{}'::jsonb)) "
    "ON CONFLICT (observed_at, board, mint) DO NOTHING"
)


def board_payload(rows: Sequence[BoardMinuteRow]) -> list[dict[str, Any]]:
    """The bound parameters of one ``INSERT``, NUL-free (T4.47b): a graduated-board
    frame named ``"…\\x00"`` killed the fold loop twice at 09:05/09:06Z on
    17/09/2026 (T4.47 had covered ``meme_tokens`` only). ``text`` refuses
    ``0x00`` and ``jsonb`` refuses ``\\u0000``, so both the columns and
    ``extra`` are cleaned here, at the database boundary."""
    import json

    payload: list[dict[str, Any]] = []
    for row in rows:
        values = {
            key: clean_text(value) if isinstance(value, str) else value
            for key, value in asdict(row).items()
        }
        extra = values.pop("extra")
        values["extra"] = (
            None if not extra else json.dumps(extra, default=str).replace("\\u0000", "")
        )
        payload.append(values)
    return payload


async def insert_board_minutes(session: AsyncSession, rows: Sequence[BoardMinuteRow]) -> int:
    if not rows:
        return 0
    await session.execute(_INSERT_BOARD_MINUTE, board_payload(rows))
    return len(rows)


#: T4.45: the statement moved to ``hunter_core.db.meme_risk_snapshots`` when the
#: executor gained a reason to write the same row (its own on-demand read of the
#: same endpoint, ``docs/RISK_ENGINE_MEME.md`` §3.5). Re-exported here so every
#: caller in this service keeps its import - one row shape, one INSERT, two
#: writers.
_RISK_COLUMNS = RISK_COLUMNS


__all__ = [
    "BoardMinuteRow",
    "TradeRow",
    "board_minute_row",
    "board_payload",
    "insert_board_minutes",
    "insert_risk_snapshot",
    "insert_trades",
    "load_tape",
    "open_bet_mints",
    "trade_rows",
]
