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
    """Start uvicorn against :data:`app`, bound to ``ApiSettings.api_port``."""
    settings = get_api_settings()
    uvicorn.run("hunter_api.main:app", host="0.0.0.0", port=settings.api_port, reload=False)
