"""ASGI entrypoint for the ``api`` process.

``uvicorn hunter_api.main:app`` (dev/reload) or the ``run()`` console entry
(``HUNTER_ROLE=api`` in the production image) both land here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import uvicorn

from hunter_api.app import create_app
from hunter_api.settings import get_api_settings
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from hunter_api.settings import ApiSettings

logger = get_logger(__name__)


def _log_internal_peer_ips(settings: ApiSettings) -> None:
    """One ``internal_peer_ips_loaded`` line at boot with the resolved set
    (T3.28d, security-reviewer finding 2 on T3.28a) -- an empty set (the
    default) or a set that no longer matches the deployment's ``web`` peer
    (a compose IP that drifted) is otherwise invisible until someone reads
    ``hunter_rate_limit_internal_peer_total`` staying at zero or greps
    ``INTERNAL_PEER_IPS`` by hand. No secret: these are compose-internal
    addresses, never credentials.
    """
    logger.info(
        "internal_peer_ips_loaded",
        internal_peer_ips=sorted(settings.internal_peer_ip_set),
    )


_api_settings = get_api_settings()
app = create_app(_api_settings)
_log_internal_peer_ips(_api_settings)


def run() -> None:
    """Start uvicorn against :data:`app`, bound to ``ApiSettings.api_port``.

    ``proxy_headers=True`` + ``forwarded_allow_ips`` tells uvicorn to trust
    ``X-Forwarded-For``/``X-Forwarded-Proto`` (and rewrite ``request.client``
    from them) only when the *direct* TCP peer is the configured platform
    ingress — see ``middleware/rate_limit.py``'s module docstring for why
    that matters for the rate-limit key.
    """
    settings = get_api_settings()
    uvicorn.run(
        "hunter_api.main:app",
        host="0.0.0.0",  # nosec B104 -- container binds all interfaces behind the platform ingress
        port=settings.api_port,
        reload=False,
        proxy_headers=True,
        forwarded_allow_ips=settings.forwarded_allow_ips,
    )
