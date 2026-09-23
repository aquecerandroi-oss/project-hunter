"""T4.82 — **the security assertion**: the two new reads sit behind exactly the
gate the ``meme_live`` router uses.

``spot_desk_markets``/``spot_orders``/``spot_positions`` (``0057``) and
``market_events`` (``0059``) are **global**: no ``organization_id``, therefore
no RLS. Nothing in the row stops a caller from seeing it, so the whole
authorisation is the route's declared dependency — which is why it is asserted
here rather than left to a reading of the router.

The design (§7a item 3) asked for these at ``/api/v1/markets/...``, whose gate
is ``PrincipalSession``: authenticated, and **not** a membership check (a
principal with zero organizations passes it). That is weaker than the gate the
equivalent meme ledger sits behind, on data that is the record of what the desk
did with real money. Everton decided on 23/09/2026 that the gate wins and the
path moves; the amendment is written into the design doc's §7a.

The minimum role is read out of the ``require_org`` closure rather than
hard-coded, and ``meme_live``'s own route is asserted alongside as the control:
if somebody weakens either one, or the two stop agreeing, this test goes red.

No database and no Docker: the app boots against unreachable URLs (see
``tests/conftest.py``), and every assertion below is either schema
introspection or a request that is refused before a query is ever built.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, cast

import pytest
from fastapi.routing import APIRoute

from hunter_api.auth.rbac import require_org
from hunter_core.domain.enums import OrganizationRole

if TYPE_CHECKING:
    import httpx
    from fastapi import FastAPI

pytestmark = pytest.mark.unit

DESK_PATH = "/api/v1/orgs/{org_id}/markets/{exchange}/{symbol}/desk"
EVENTS_PATH = "/api/v1/orgs/{org_id}/markets/{exchange}/{symbol}/events"
MEME_LIVE_PATH = "/api/v1/orgs/{org_id}/meme/live"
"""The control: the gate T4.82 was told to copy, byte for byte."""

NEW_PATHS = (DESK_PATH, EVENTS_PATH)


def _api_routes(node: Any) -> Iterator[APIRoute]:
    """Every ``APIRoute`` reachable from ``node``.

    ``include_router`` wraps each router in a ``_IncludedRouter`` in this
    FastAPI version — a ``BaseRoute`` with no ``routes`` of its own, holding
    the real ``APIRouter`` under ``original_router``. A flat walk of
    ``app.routes`` therefore finds four routes and none of the interesting
    ones, which is a silently *green* test rather than a red one: every lookup
    returns ``None`` and every comparison of two ``None``s passes. Hence
    ``test_the_route_declares_a_minimum_role``, which fails on ``None``.
    """
    for route in getattr(node, "routes", ()):
        if isinstance(route, APIRoute):
            yield route
        else:
            yield from _api_routes(getattr(route, "original_router", route))


def _minimum_role(app: FastAPI, path: str) -> OrganizationRole | None:
    """The floor declared by the ``require_org(...)`` guarding ``path``.

    ``require_org(minimum)`` returns a closure over ``minimum``
    (``auth/rbac.py``); reading it back is what lets this test assert the
    *declared* floor instead of re-asserting a literal somebody copied.
    ``None`` means the route declares no ``require_org`` at all — which, for
    these tables, is the failure this whole module exists to catch.
    """
    marker = require_org(OrganizationRole.VIEWER).__qualname__
    for route in _api_routes(app):
        if route.path != path:
            continue
        for dependency in route.dependant.dependencies:
            call = dependency.call
            if call is None or getattr(call, "__qualname__", None) != marker:
                continue
            closure = getattr(call, "__closure__", None) or ()
            for cell in closure:
                if isinstance(cell.cell_contents, OrganizationRole):
                    return cell.cell_contents
    return None


class TestTheRoutesExistWhereTheGateCanReachThem:
    @pytest.mark.parametrize("path", NEW_PATHS)
    def test_the_route_is_registered_under_the_tenant_prefix(self, app: FastAPI, path: str) -> None:
        """``require_org`` resolves ``{org_id}`` out of the path; a route
        without it structurally cannot be guarded by one."""
        paths = cast("dict[str, Any]", app.openapi()["paths"])
        assert path in paths
        assert path.startswith("/api/v1/orgs/{org_id}/")

    @pytest.mark.parametrize("path", NEW_PATHS)
    def test_the_route_is_a_read_only_get(self, app: FastAPI, path: str) -> None:
        """Design §6: "Sem POST". Nothing on this screen moves money."""
        paths = cast("dict[str, dict[str, Any]]", app.openapi()["paths"])
        assert set(paths[path]) == {"get"}


class TestTheGateIsTheMemeLiveGate:
    @pytest.mark.parametrize("path", NEW_PATHS)
    def test_the_route_declares_a_minimum_role(self, app: FastAPI, path: str) -> None:
        assert _minimum_role(app, path) is not None, (
            f"{path} reads global, RLS-free tables and declares no require_org"
        )

    @pytest.mark.parametrize("path", NEW_PATHS)
    def test_the_minimum_is_the_same_one_meme_live_declares(self, app: FastAPI, path: str) -> None:
        assert _minimum_role(app, path) == _minimum_role(app, MEME_LIVE_PATH)

    @pytest.mark.parametrize("path", NEW_PATHS)
    def test_the_minimum_is_viewer(self, app: FastAPI, path: str) -> None:
        """Spelled out as well as compared, so the pair moving *together* down
        the ladder still fails."""
        assert _minimum_role(app, path) == OrganizationRole.VIEWER


class TestAnUnauthenticatedCallerNeverReachesTheTables:
    @pytest.mark.parametrize("path", NEW_PATHS)
    async def test_without_a_bearer_token_it_is_401_before_any_query(
        self, client: httpx.AsyncClient, path: str
    ) -> None:
        """The database URL these tests boot against is unreachable, so a 401
        (rather than a 500) is itself the proof that the gate fires while
        dependencies resolve — before a session is ever opened."""
        url = (
            path.replace("{org_id}", "00000000-0000-4000-8000-000000000001")
            .replace("{exchange}", "binance")
            .replace("{symbol}", "ZECUSDT")
        )
        response = await client.get(url)
        assert response.status_code == 401
        assert response.headers["content-type"].startswith("application/problem+json")
