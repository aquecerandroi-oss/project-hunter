#!/usr/bin/env bash
# PROJECT HUNTER — single entrypoint for the api+workers image.
#
# One image, many roles (ARCHITECTURE.md §1.7): HUNTER_ROLE picks the process
# that runs. Run one role per container; worker roles execute their package
# entrypoints and fail explicitly if that package has no entrypoint yet.
#
# An explicit command (e.g. `docker run hunter-api:dev python -c "..."` or
# `... id -u` for verification/debugging) always wins over role dispatch —
# standard docker-entrypoint convention — so only fall through to
# role dispatch when no command was given.
#
# `migrate` and `seed` are image-only actions, not real
# hunter_core.settings.Settings.hunter_role values — that Settings model
# (packages/core/hunter_core/settings.py) validates HUNTER_ROLE against a
# strict Literal of actual long-running roles, and *any* Settings()
# construction downstream (alembic's env.py included) raises immediately if
# HUNTER_ROLE is "migrate"/"seed". So those two are selected via the
# separate HUNTER_COMMAND variable instead, leaving HUNTER_ROLE itself untouched
# (image default "api", itself a valid Settings literal) — only HUNTER_ROLE
# picks among the real api/worker roles.
set -euo pipefail

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

role="${HUNTER_COMMAND:-${HUNTER_ROLE:-all}}"

case "$role" in
  api)
    # apps/api/hunter_api/main.py exposes a `run()` that starts uvicorn but
    # has no `if __name__ == "__main__"` guard, so invoke it directly.
    exec python -c "from hunter_api.main import run; run()"
    ;;
  migrate)
    exec alembic -c infra/migrations/alembic.ini upgrade head
    ;;
  seed)
    exec python infra/scripts/seed.py
    ;;
  market)
    exec python -m hunter_market_worker
    ;;
  scanner | strategy | execution | analytics)
    exec python -m "hunter_${role}_worker"
    ;;
  all)
    echo "role all is not supported yet: run one HUNTER_ROLE per container (M1)"
    exit 64
    ;;
  *)
    echo "unknown HUNTER_ROLE: ${role}" >&2
    exit 64
    ;;
esac
