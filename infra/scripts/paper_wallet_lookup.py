"""Read-only prerequisites for ``open_paper_wallet.py``: the quote, and the
resolved organization/workspace/already-open check.

Split out for the file-size budget (CLAUDE.md: "no file over 350 lines, split
by responsibility, not by line count"), not a change of ownership: everything
here only *reads* — the network, or the database as ``hunter_worker`` — and
raises :class:`Refused` when a prerequisite fails. Nothing in this module
ever writes a row.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import httpx
from sqlalchemy import text

from hunter_core.portfolio.opening import PAPER_FX_POLICY
from hunter_exchanges.binance_spot import normalize
from hunter_exchanges.binance_spot.http import BASE_URL

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

PAIR = PAPER_FX_POLICY.pair
"""``USDTBRL`` — the pair the paper wallet's opening policy accepts."""

SOURCE = "binance.spot.ticker"
"""The only source this script implements, and the default of ``--fx-source``.
Must match ``FxPolicy.source`` (``hunter_core.portfolio.opening.
PAPER_FX_POLICY``) for the observation this script writes to be usable by
``open_paper_wallet`` at all — a source it does not declare cannot open a
wallet ("fonte inválida não abre", T3.11)."""

TICKER_ENDPOINT = "ticker/24hr"
"""Which of the two candidate endpoints (``ticker/24hr`` vs ``ticker/price``)
this script uses, printed for the record every run."""


class Refused(RuntimeError):
    """A prerequisite failed; nothing was written."""


async def fetch_quote(source: str) -> tuple[Decimal, dict[str, Any]]:
    """The current ``USDTBRL`` price from Binance spot, and the raw response.

    Uses ``ticker/24hr`` rather than ``ticker/price``: the former carries
    ``closeTime`` (the exchange's own clock, used as ``observed_at``);
    the latter carries no timestamp at all, only a price.

    A direct, one-shot ``httpx`` call rather than
    ``hunter_exchanges.binance_spot.rest.BinanceSpotRestClient``: that client
    normalizes the ticker and discards the raw body
    (``BinanceSpotRestClient.fetch_ticker``), while ``fx_observations.raw``
    needs the body itself, and its transport is a private attribute of the
    class (``SpotHttp``, reached only through ``_http`` — reportPrivateUsage).
    A single request from an operator script does not need that client's
    token-bucket/retry machinery, built for a continuous poller; ``normalize``
    itself is still the public parser T3.11's future collector will use too.
    """
    if source != SOURCE:
        raise Refused(f"--fx-source {source!r} is not implemented; only {SOURCE!r} is")
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        response = await client.get("/api/v3/ticker/24hr", params={"symbol": PAIR})
        response.raise_for_status()
        raw: dict[str, Any] = response.json()
    ticker = normalize.parse_ticker_24h(raw)
    return ticker.last, raw


async def resolve_organization(session: AsyncSession, slug: str) -> uuid.UUID:
    org_id = await session.scalar(
        text("SELECT id FROM organizations WHERE slug = :slug AND deleted_at IS NULL"),
        {"slug": slug},
    )
    if org_id is None:
        raise Refused(f"no organization with slug {slug!r}")
    return org_id


async def resolve_workspace(session: AsyncSession, org_id: uuid.UUID, name: str) -> uuid.UUID:
    """The organization's workspace named ``name``.

    Workspaces have no slug column (only organizations do,
    ``hunter_core.db.models.identity.Organization.slug``); this matches on
    ``workspaces.name``, which is what the operator actually types.

    ``workspaces.name`` is not unique (Astra, review of this diff, MUST-FIX
    1): two live workspaces of the same organization can share a name, and
    the opening this resolves into is permanent — a ``LIMIT 1`` would pick
    one of them arbitrarily and there is no undo. Every match is fetched and
    an ambiguity is a refusal, not a coin flip.
    """
    rows = (
        (
            await session.execute(
                text(
                    "SELECT id FROM workspaces WHERE organization_id = :org AND name = :name "
                    "AND deleted_at IS NULL"
                ),
                {"org": org_id, "name": name},
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        raise Refused(f"no workspace named {name!r} in this organization")
    if len(rows) > 1:
        raise Refused(
            f"{len(rows)} workspaces named {name!r} in this organization ({rows!r}); "
            "opening is permanent and this script will not guess which one — rename the "
            "duplicates or open against the workspace id directly"
        )
    workspace_id = rows[0]
    return workspace_id


async def refuse_if_already_open(session: AsyncSession, org_id: uuid.UUID) -> None:
    found = await session.scalar(
        text(
            "SELECT 1 FROM portfolios WHERE organization_id = :org "
            "AND type = 'paper' AND NOT is_arena LIMIT 1"
        ),
        {"org": org_id},
    )
    if found is not None:
        raise Refused(
            "this organization already has its principal paper wallet; there is no second "
            "opening (D7) — a repeat run refuses instead of silently no-op'ing"
        )
