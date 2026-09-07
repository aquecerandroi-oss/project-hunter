#!/usr/bin/env python3
"""Open an organization's principal paper wallet — the operator's script.

    uv run python infra/scripts/open_paper_wallet.py \\
        --org ever --workspace principal --capital-brl 100000 \\
        --fx-source binance.spot.ticker
    uv run python infra/scripts/open_paper_wallet.py --org ever --workspace principal --dry-run

Fetches ``USDTBRL`` from Binance's public spot REST
(``packages/exchange-adapters/hunter_exchanges/binance_spot``, commit
``078d6ef``): ``GET /api/v3/ticker/24hr`` for one symbol, weight 2 — chosen
over ``ticker/price`` because it carries the exchange's own ``closeTime``, so
the observation is stamped by Binance's clock rather than the operator's, and
``lastPrice`` is exactly "the current price" the brief asks for. Persists the
quote to ``fx_observations`` as ``hunter_worker`` (T3.11's role;
``PAPER_WORKER_APPEND_TABLES``, DATABASE.md §18.9), then opens the wallet with
``hunter_core.portfolio.opening.open_paper_wallet`` (T3.3) — the single write
path for the wallet, its anchor, its lock row and the first point of the
equity curve, all in one commit.

``--dry-run`` fetches and prints the quote; nothing is written, not even the
lookup transaction touches a write table. Refuses (non-zero exit, nothing
written) when the organization or workspace does not resolve, or when the
organization already has a principal paper wallet — opening one is a
once-per-organization act (D7: "carteira principal é uma só e permanente"),
never a route to a reset. A second run against the same organization is
therefore a refusal, not a second wallet or a second FX observation: this is
what makes the script idempotent, by refusing loudly rather than silently
no-op'ing.

No network call happens under any lock: the quote is fetched before any
database session is opened at all.

Never reads ``.env``: every connection string comes from ``hunter_core.
settings.Settings``, exactly like the other operator scripts
(``infra/scripts/activate_strategy_version.py``).
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import httpx
from sqlalchemy import text

from hunter_core.db.models.fx import FxObservation
from hunter_core.db.repositories.fx import FxObservationRepository
from hunter_core.db.session import (
    create_engine,
    create_session_factory,
    role_session,
    tenant_session,
)
from hunter_core.domain.types import utcnow, uuid7
from hunter_core.logging import get_logger
from hunter_core.portfolio.opening import (
    DEFAULT_CAPITAL_BRL,
    PAPER_FX_POLICY,
    FxObservationRejected,
    WalletAlreadyOpen,
    open_paper_wallet,
)
from hunter_core.settings import Settings
from hunter_exchanges.binance_spot import normalize
from hunter_exchanges.binance_spot.http import BASE_URL

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = get_logger(__name__)

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
    ``closeTime`` (the exchange's own clock, used as ``observed_at`` below);
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


async def _resolve_organization(session: AsyncSession, slug: str) -> uuid.UUID:
    org_id = await session.scalar(
        text("SELECT id FROM organizations WHERE slug = :slug AND deleted_at IS NULL"),
        {"slug": slug},
    )
    if org_id is None:
        raise Refused(f"no organization with slug {slug!r}")
    return org_id


async def _resolve_workspace(session: AsyncSession, org_id: uuid.UUID, name: str) -> uuid.UUID:
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


async def _refuse_if_already_open(session: AsyncSession, org_id: uuid.UUID) -> None:
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


async def _write_observation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    rate: Decimal,
    source: str,
    raw: dict[str, Any],
) -> uuid.UUID:
    """Persist the quote as ``hunter_worker`` (T3.11's role) and hand back its id."""
    observation_id = uuid7()
    observed_at = normalize.parse_ticker_24h(raw).ts
    async with role_session(session_factory, db_role="hunter_worker") as session:
        session.add(
            FxObservation(
                id=observation_id,
                pair=PAIR,
                rate=rate,
                source=source,
                observed_at=observed_at,
                available_at=utcnow(),
                raw=raw,
            )
        )
    return observation_id


async def _run(args: argparse.Namespace) -> int:
    settings = Settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        rate, raw = await fetch_quote(args.fx_source)
        print(f"USDTBRL {rate} from Binance spot {TICKER_ENDPOINT} (closeTime observed)")

        async with role_session(factory, db_role="hunter_worker") as lookup:
            org_id = await _resolve_organization(lookup, args.org)
            workspace_id = await _resolve_workspace(lookup, org_id, args.workspace)
            await _refuse_if_already_open(lookup, org_id)

        if args.dry_run:
            print("--dry-run: nothing written")
            return 0

        fx_observation_id = await _write_observation(
            factory, rate=rate, source=args.fx_source, raw=raw
        )
        print(f"fx_observations: wrote {fx_observation_id} at rate {rate}")

        async with tenant_session(factory, org_id) as session:
            fx = await FxObservationRepository(session).get(fx_observation_id)
            if fx is None:  # pragma: no cover - just written, same database
                raise Refused(f"could not read back fx_observation {fx_observation_id}")
            result = await open_paper_wallet(
                session,
                organization_id=org_id,
                workspace_id=workspace_id,
                fx=fx,
                capital_brl=args.capital_brl,
                actor_id="operator:open_paper_wallet",
            )
        print(
            f"opened portfolio {result.portfolio_id}: "
            f"R${result.conversion.origin_amount} -> {result.conversion.credited_amount} USDT "
            f"at {result.conversion.rate} (residual {result.conversion.conversion_residual})"
        )
        return 0
    except Refused as refusal:
        print(f"REFUSED: {refusal}")
        return 1
    except FxObservationRejected as refusal:
        print(f"REFUSED (fx observation invalid): {refusal.reason}")
        return 1
    except WalletAlreadyOpen as refusal:
        print(f"REFUSED (concurrent opening): {refusal}")
        return 1
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--org", required=True, help="organizations.slug")
    parser.add_argument("--workspace", required=True, help="workspaces.name within --org")
    parser.add_argument(
        "--capital-brl",
        type=Decimal,
        default=DEFAULT_CAPITAL_BRL,
        help="R$ to convert and credit (default: R$100.000, the directive's number)",
    )
    parser.add_argument(
        "--fx-source",
        default=SOURCE,
        choices=[SOURCE],
        help="the only source implemented (must match the wallet's FxPolicy.source)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="fetch and print the quote; write nothing"
    )
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
