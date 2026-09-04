"""The worker process shell: logging, Sentry, heartbeat, health endpoints, shutdown.

ARCHITECTURE.md §1.7 ("uma imagem, varios papeis") and §11 (heartbeat, health,
metrics). Every ``services/*`` entrypoint is expected to be a thin
``async def main(runtime: WorkerRuntime) -> None`` registered in
:data:`RoleRegistry` and driven by :meth:`WorkerRuntime.run`. Composing
``HUNTER_ROLE=all`` out of the registry is left to a later task (T05+) — this
module only defines the registry those tasks populate.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import socket
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from hunter_core import __version__
from hunter_core.db.session import check_database, create_engine
from hunter_core.domain.types import utcnow
from hunter_core.logging import configure_logging, get_logger
from hunter_core.observability import init_sentry, metrics_asgi_app, worker_errors_total
from hunter_core.redis import check_redis, create_redis, keys

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncEngine
    from starlette.types import ASGIApp

    from hunter_core.settings import Settings

HEARTBEAT_INTERVAL_S = 10
HEARTBEAT_TTL_S = 30

logger = get_logger(__name__)


class WorkerRuntime:
    """Shared shell for every worker/api process (one per ``HUNTER_ROLE``)."""

    def __init__(
        self,
        role: str,
        settings: Settings,
        *,
        instance: str | None = None,
        engine: AsyncEngine | None = None,
        redis_client: redis_asyncio.Redis | None = None,
    ) -> None:
        self.role = role
        self.settings = settings
        self.instance = instance or f"{socket.gethostname()}:{os.getpid()}"
        self.engine: AsyncEngine = engine if engine is not None else create_engine(settings)
        self.redis: redis_asyncio.Redis = (
            redis_client if redis_client is not None else create_redis(settings)
        )
        self._error_count = 0
        self._last_success: datetime | None = None
        self.app: ASGIApp = self._build_app()

    def mark_success(self) -> None:
        """Record a successful unit of work — reflected in the next heartbeat."""
        self._last_success = utcnow()

    def mark_error(self) -> None:
        """Record a failed unit of work — increments the heartbeat counter and metric."""
        self._error_count += 1
        worker_errors_total.labels(role=self.role).inc()

    @property
    def error_count(self) -> int:
        """Errors recorded since process start (read-only; see :meth:`mark_error`)."""
        return self._error_count

    @property
    def last_success(self) -> datetime | None:
        """When :meth:`mark_success` was last called, if ever."""
        return self._last_success

    async def write_heartbeat(self) -> None:
        """Write ``hb:{role}:{instance}`` (HASH, 30s TTL) — ARCHITECTURE.md §5.3/§11."""
        key = keys.heartbeat(self.role, self.instance)
        await self.redis.hset(
            key,
            mapping={
                "ts": utcnow().isoformat(),
                "last_success": self._last_success.isoformat() if self._last_success else "",
                "errors": str(self._error_count),
                "version": __version__,
            },
        )
        await self.redis.expire(key, HEARTBEAT_TTL_S)

    async def _heartbeat_loop(self) -> None:
        while True:
            try:
                await self.write_heartbeat()
            except Exception:
                logger.warning("heartbeat_write_failed", role=self.role)
            await asyncio.sleep(HEARTBEAT_INTERVAL_S)

    def _build_app(self) -> Starlette:
        async def health(_request: Request) -> JSONResponse:
            return JSONResponse({"status": "ok"})

        async def ready(_request: Request) -> JSONResponse:
            db_ok = await check_database(self.engine)
            redis_ok = await check_redis(self.redis)
            details = {"database": db_ok, "redis": redis_ok}
            return JSONResponse(details, status_code=200 if db_ok and redis_ok else 503)

        return Starlette(
            routes=[
                Route("/health", health),
                Route("/ready", ready),
                Mount("/metrics", app=metrics_asgi_app()),
            ]
        )

    async def run(self, main: Callable[[WorkerRuntime], Awaitable[None]]) -> None:
        """Wire logging/Sentry, start the heartbeat and health server, then run ``main``.

        ``main`` is cancelled on SIGTERM/SIGINT (or when it raises on its own);
        the heartbeat loop and health server are always torn down afterwards.
        """
        configure_logging(self.settings, self.role)
        init_sentry(self.settings, self.role)

        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(NotImplementedError, RuntimeError):
                loop.add_signal_handler(sig, stop_event.set)

        heartbeat_task = asyncio.ensure_future(self._heartbeat_loop())
        server = uvicorn.Server(
            uvicorn.Config(
                self.app,
                port=self.settings.health_port,
                lifespan="off",
                log_config=None,
            )
        )
        server_task = asyncio.ensure_future(server.serve())
        main_task = asyncio.ensure_future(main(self))
        stop_task = asyncio.ensure_future(stop_event.wait())

        try:
            await asyncio.wait({main_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
            if not main_task.done():
                main_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await main_task
            else:
                error = main_task.exception()
                if error is not None:
                    raise error
        finally:
            stop_task.cancel()
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task
            server.should_exit = True
            await server_task


RoleEntrypoint = Callable[[WorkerRuntime], Awaitable[Any]]

RoleRegistry: dict[str, RoleEntrypoint] = {}
"""role -> entrypoint. Populated by ``services/*`` (T05 onward); empty here by
design. ``HUNTER_ROLE=all`` composition (running every registered entrypoint
as a concurrent task) is out of scope for T03.
"""
