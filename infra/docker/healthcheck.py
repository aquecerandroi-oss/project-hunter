#!/usr/bin/env python3
"""HEALTHCHECK probe for the api+workers image.

No `curl` in the `python:3.12-slim-bookworm` runtime stage, so this hits
``/health`` with the stdlib. ``HUNTER_ROLE=api`` serves it on ``API_PORT``
(default 8000, see apps/api/hunter_api/main.py); every other role would
serve it on ``HEALTH_PORT`` (default 8001) via hunter_core.runtime.WorkerRuntime
once M1 gives it a real entrypoint — until then those roles exit immediately
(see entrypoint.sh) and Docker simply never gets to run this against them.
"""

from __future__ import annotations

import os
import sys
import urllib.request

role = os.environ.get("HUNTER_ROLE", "all")
port = (
    os.environ.get("API_PORT", "8000") if role == "api" else os.environ.get("HEALTH_PORT", "8001")
)
url = f"http://127.0.0.1:{port}/health"

try:
    with urllib.request.urlopen(url, timeout=2) as response:
        sys.exit(0 if response.status == 200 else 1)
except Exception:
    sys.exit(1)
