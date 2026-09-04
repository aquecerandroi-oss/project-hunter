"""ASGI entrypoint for the ``api`` process.

``uvicorn hunter_api.main:app`` (dev/reload) or the ``run()`` console entry
(``HUNTER_ROLE=api`` in the production image) both land here.
"""

from __future__ import annotations

import uvicorn

from hunter_api.app import create_app
from hunter_api.settings import get_api_settings

app = create_app(get_api_settings())


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
