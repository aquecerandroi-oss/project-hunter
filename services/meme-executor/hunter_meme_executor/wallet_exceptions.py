"""Everton's audited per-mint exception to §3.2's ``wallet_unrecognized_holdings``
(decision 2026-09-28, ``obsidian/06-DECISIONS/2026-09-28-excecao-auditada-token-golpe.md``).

A phishing token frozen by its issuer cannot be moved, burned or closed, so the
contract's remedy ("zero the balance") is impossible and check 17 would refuse
every entry forever. The owner records an exception — Postgres only, by the
audited CLI ``infra/scripts/wallet_holding_exception.py`` — for **one wallet,
one token program, one mint**, with the balance and state he verified.

What an exception does, and only this: it takes its mint off the list of
unrecognized mints **while the chain still shows what was verified** — every
account of that mint in the read is under the recorded program, with the
recorded decimals, not opaque, the total at most the recorded atoms (a buy on
top is named again), and each account ``frozen`` when the row requires it (a
thaw makes the remedy possible again, so the mint is named again). A state the
parser did not recognize never passes, not even under ``--allow-unfrozen``
(Astra, design review). Anything else leaves the mint named: fail closed.

What it never does: mark the mint as recognized. This module is the table's
only runtime reader (a test pins it), and its only caller is the holdings
verdict — no buy, sell, exit, sizing or equity path ever sees an exception.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Final

from sqlalchemy import text

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_meme_executor.chain import TokenHolding

__all__ = ["EXCEPTIONS_TABLE", "HoldingException", "active_exceptions", "split_excepted"]

EXCEPTIONS_TABLE: Final = "meme_wallet_holding_exceptions"
_UNFROZEN_OK: Final = frozenset({"initialized", "frozen"})
"""Under ``require_frozen = false`` the account must still be in a state the
parser recognized — never an absent or unknown one."""

_ACTIVE = text(
    "SELECT token_program, mint, max_atoms, decimals, require_frozen, id, created_at "  # noqa: S608
    f"FROM {EXCEPTIONS_TABLE} "  # a constant table name
    "WHERE wallet = :wallet AND revoked_at IS NULL"
)


@dataclass(frozen=True, slots=True)
class HoldingException:
    """One active row: what the owner verified, and nothing he did not."""

    program: str
    mint: str
    max_atoms: int
    decimals: int
    require_frozen: bool
    id: str
    """Recorded by the admission that used it (database-architect review): a
    verdict is reused for up to 30 s without re-reading, so the row that decided
    cannot be reconstructed from ``created_at``/``revoked_at`` alone."""
    created_at: datetime

    def as_json(self) -> dict[str, str]:
        return {
            "mint": self.mint,
            "exception_id": self.id,
            "created_at": self.created_at.isoformat(),
        }


async def active_exceptions(session: AsyncSession, *, wallet: str) -> tuple[HoldingException, ...]:
    """This wallet's unrevoked rows. Run in the recognized set's transaction."""
    rows = await session.execute(_ACTIVE, {"wallet": wallet})
    return tuple(
        HoldingException(str(r[0]), str(r[1]), int(r[2]), int(r[3]), bool(r[4]), str(r[5]), r[6])
        for r in rows
    )


def _covered(accounts: Sequence[TokenHolding], rule: HoldingException | None) -> bool:
    if rule is None or not accounts:
        return False
    states = _UNFROZEN_OK if not rule.require_frozen else frozenset({"frozen"})
    return (
        all(
            h.program == rule.program
            and h.decimals == rule.decimals
            and not h.opaque
            and h.state in states
            for h in accounts
        )
        and sum(h.amount for h in accounts) <= rule.max_atoms
    )


def split_excepted(
    named: Sequence[str],
    holdings: Iterable[TokenHolding],
    exceptions: Iterable[HoldingException],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """``named`` (``unrecognized_mints``' answer) → ``(unrecognized, excepted)``,
    order kept. A mint is excepted only when **every** account of it in the read
    is covered by its one row (an account under another program is not)."""
    rules = {e.mint: e for e in exceptions}
    by_mint: dict[str, list[TokenHolding]] = {}
    for h in holdings:
        by_mint.setdefault(h.mint, []).append(h)
    unrecognized: list[str] = []
    excepted: list[str] = []
    for mint in named:
        covered = _covered(by_mint.get(mint, []), rules.get(mint))
        (excepted if covered else unrecognized).append(mint)
    return tuple(unrecognized), tuple(excepted)
