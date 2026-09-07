#!/usr/bin/env python3
"""Open an organization's principal paper wallet — the operator's script.

    uv run python infra/scripts/open_paper_wallet.py --org ever --workspace principal --dry-run
    uv run python infra/scripts/open_paper_wallet.py \\
        --org ever --workspace principal --yes ever --actor operator@example.com

Opening credits a fixed R$100.000 (the directive's §1 number, not a flag —
``hunter_core.portfolio.opening.DEFAULT_CAPITAL_BRL``) and is permanent and
irreversible (D7): there is no undo and no second opening. Nothing is ever
written without an explicit, literal ``--yes <the same slug given to --org>``
— omit it (or get it wrong) and the script only resolves, previews and prints
what it would do; ``--actor`` (an email or a free-text handle, naming the
person confirming this, never the script) is required together with ``--yes``
and is what ``audit_logs`` remembers instead of ``open_paper_wallet.py``
itself (security review of ``2688ef1``, S3).

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
import getpass
import socket
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from paper_wallet_confirmation import is_confirmed, resolve_actor
from paper_wallet_lookup import (
    PAIR,
    SOURCE,
    TICKER_ENDPOINT,
    Refused,
    fetch_quote,
    refuse_if_already_open,
    resolve_organization,
    resolve_workspace,
)

from hunter_core.audit import AuditEvent, SqlAuditSink
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
    FxObservationRejected,
    ScopeViolation,
    WalletAlreadyOpen,
    open_paper_wallet,
)
from hunter_core.settings import Settings
from hunter_exchanges.binance_spot import normalize

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = get_logger(__name__)


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
    # ``--actor`` names the person confirming a permanent, irreversible act
    # (D7) and must be present whenever ``--yes`` is, even if ``--yes`` turns
    # out not to match ``--org`` below — the pairing is about intent, checked
    # before anything else runs (S3: "auditoria com a pessoa").
    if args.yes is not None and args.actor is None:
        print("REFUSED: --actor <email or id> is required together with --yes")
        return 1

    settings = Settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        rate, raw = await fetch_quote(args.fx_source)
        print(f"USDTBRL {rate} from Binance spot {TICKER_ENDPOINT} (closeTime observed)")
        print(f"opening capital is fixed at R${DEFAULT_CAPITAL_BRL} (directive §1; not a flag)")

        async with role_session(factory, db_role="hunter_worker") as lookup:
            org_id = await resolve_organization(lookup, args.org)
            workspace_id = await resolve_workspace(lookup, org_id, args.workspace)
            await refuse_if_already_open(lookup, org_id)

        # Confirmation: nothing below this point writes anything unless
        # ``--yes`` repeats ``--org``'s slug *literally* (D7 — the opening is
        # permanent and irreversible, so the safe default is a preview, never
        # a write).
        if args.yes is not None and args.yes != args.org:
            raise Refused(
                f"--yes {args.yes!r} does not repeat --org {args.org!r} exactly; nothing written"
            )
        confirmed = is_confirmed(org_slug=args.org, yes=args.yes)

        if args.dry_run or not confirmed:
            if args.dry_run:
                print("--dry-run: nothing written")
            else:
                print(
                    "no confirmation: nothing written. Opening the principal paper wallet "
                    f"is permanent and irreversible (D7) — pass --yes {args.org} and "
                    "--actor <email or id> to confirm."
                )
            return 0

        async with role_session(factory, db_role="hunter_worker") as lookup:
            actor_type, actor_id_str = await resolve_actor(lookup, org_id, args.actor)

        fx_observation_id = await _write_observation(
            factory, rate=rate, source=args.fx_source, raw=raw
        )
        print(f"fx_observations: wrote {fx_observation_id} at rate {rate}")

        # As ``hunter_worker``, with ``app.current_org`` set anyway (0007_paper_roles,
        # DATABASE.md §19.6). The opening writes the wallet, its lock row, its anchor
        # **and the first point of the equity curve**, in one transaction (§18.2) — and
        # since 0007 the curve is read-only to ``hunter_app``, because it is the evidence
        # a resume reads. Opening a wallet is an operator act, the same class as removing
        # a tenant (§15.4), not a request handler; there is no HTTP route for it.
        # ``open_paper_wallet``'s own ``verify_scope`` (default True) re-reads every
        # row this writes by ``organization_id`` before returning — the role above
        # is BYPASSRLS, so that re-check, not Postgres's RLS, is what would catch a
        # wrongly-scoped write here.
        async with tenant_session(factory, org_id, db_role="hunter_worker") as session:
            fx = await FxObservationRepository(session).get(fx_observation_id)
            if fx is None:  # pragma: no cover - just written, same database
                raise Refused(f"could not read back fx_observation {fx_observation_id}")
            result = await open_paper_wallet(
                session,
                organization_id=org_id,
                workspace_id=workspace_id,
                fx=fx,
                actor_id=actor_id_str,
            )
            # The person, not the script: S3's "auditoria nomeia o script, não a
            # pessoa". A second, additive row rather than changing what
            # ``open_paper_wallet`` itself writes for ``portfolio.opened`` (its
            # signature only grew ``verify_scope``) — this one carries
            # ``actor_type`` and the operator's host/OS user, for the SSH log.
            await SqlAuditSink(session).record(
                AuditEvent(
                    actor_type=actor_type,
                    actor_id=actor_id_str,
                    organization_id=org_id,
                    action="portfolio.opened.confirmed_by",
                    entity_type="portfolio",
                    entity_id=str(result.portfolio_id),
                    metadata={
                        "actor_input": args.actor,
                        "hostname": socket.gethostname(),
                        "os_user": getpass.getuser(),
                        "org_slug": args.org,
                        "workspace": args.workspace,
                    },
                )
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
    except ScopeViolation as violation:
        print(f"REFUSED (scope violation, rolled back): {violation}")
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
        "--fx-source",
        default=SOURCE,
        choices=[SOURCE],
        help="the only source implemented (must match the wallet's FxPolicy.source)",
    )
    parser.add_argument(
        "--yes",
        metavar="ORG_SLUG",
        default=None,
        help=(
            "repeat --org's slug literally to confirm: opening the principal paper "
            "wallet is permanent and irreversible (D7). Without a matching --yes, "
            "this script only resolves, previews and writes nothing."
        ),
    )
    parser.add_argument(
        "--actor",
        default=None,
        help=(
            "who is confirming this — required together with --yes. An email of an "
            "existing member of --org is recorded in audit_logs as actor_type=user; "
            "anything else is recorded as actor_type=system, actor_id=operator:<text>."
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="fetch and print the quote; write nothing"
    )
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
