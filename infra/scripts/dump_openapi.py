#!/usr/bin/env python3
"""Print the API's OpenAPI document as JSON on stdout — no server needed.

``create_app`` only wires routers, middleware and an (unconnected)
SQLAlchemy engine / Redis client into ``app.state``; both clients are lazy
(no socket touched until a query/command runs — see ``apps/api/tests/conftest.py``),
so building the FastAPI app and reading ``.openapi()`` off it needs no
Postgres, no Redis, and no running process at all. Dummy/unreachable URLs
below mirror the ``api_settings`` fixture there.

``packages/shared-types``'s ``gen:types`` pipes this into
``openapi-typescript`` (root ``package.json``):

    uv run python infra/scripts/dump_openapi.py > packages/shared-types/openapi.json
    openapi-typescript packages/shared-types/openapi.json -o packages/shared-types/src/generated/api.d.ts

Usage:
    uv run python infra/scripts/dump_openapi.py > packages/shared-types/openapi.json
"""

from __future__ import annotations

import json
import sys

from pydantic import SecretStr

from hunter_api.app import create_app
from hunter_api.settings import ApiSettings

DUMMY_DATABASE_URL = "postgresql+asyncpg://hunter:hunter@localhost:59999/hunter_dump_unreachable"
DUMMY_REDIS_URL = "redis://localhost:59998/0"


def build_settings() -> ApiSettings:
    return ApiSettings(
        hunter_env="development",
        database_url=SecretStr(DUMMY_DATABASE_URL),
        redis_url=SecretStr(DUMMY_REDIS_URL),
        web_origin="http://localhost:3000",
        cors_allowed_origins=["http://localhost:3000"],
    )


def main() -> int:
    app = create_app(build_settings())
    json.dump(app.openapi(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
