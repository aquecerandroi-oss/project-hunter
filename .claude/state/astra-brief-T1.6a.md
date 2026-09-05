# Task T1.6a — Run the market worker continuously in Docker (PROJECT HUNTER, Milestone 1)

You are Astra, an implementer on an existing monorepo. Read `CLAUDE.md` (hard rules) and `docs/plans/M1.md` (row T1.6) first. Do NOT commit. Do NOT read `.env`. Do NOT touch anything outside the repository `C:/dev/project-hunter`. Touch ONLY the files listed below.

## Files you may modify
- `infra/docker/entrypoint.sh`
- `infra/docker/docker-compose.yml`
- `infra/docker/docker-compose.test.yml` (only if it defines a worker service)
- `infra/docker/Dockerfile.api-workers`
- `docs/DEPLOYMENT.md` (only the section describing compose services / worker roles)

## Context
- Single image `hunter-api:dev` built from `infra/docker/Dockerfile.api-workers` serves the API and all workers; `entrypoint.sh` dispatches on `HUNTER_ROLE` / `HUNTER_COMMAND`. Today roles `market|scanner|strategy|execution|analytics|all` print "no entrypoint yet" and exit 0.
- A sibling task is creating the package `hunter_market_worker` under `services/market-worker/` with a `__main__.py` (so `python -m hunter_market_worker` starts it) and it registers itself in `hunter_core.runtime.RoleRegistry["market"]`. The other four worker packages (`hunter_scanner_worker`, `hunter_strategy_worker`, `hunter_execution_worker`, `hunter_analytics_worker`) still have no `__main__.py`.
- Workers expose `/health`, `/ready`, `/metrics` on `HEALTH_PORT` (default 8001) via `hunter_core.runtime.WorkerRuntime`.
- uv workspace: root `pyproject.toml` lists all members; check how the Dockerfile currently installs the workspace (`uv sync --all-packages`?) and make sure the five `services/*-worker` packages are copied into the image and installed (they are workspace members; verify the `COPY` lines include `services/`).

## What to do
1. `entrypoint.sh`: replace the placeholder case with real dispatch: `market` → `exec python -m hunter_market_worker`; `scanner|strategy|execution|analytics` → `exec python -m hunter_<role>_worker` (they will fail with "No module named ... __main__" until those packages exist — that is acceptable and honest; do not fake them); `all` → print an explicit message "role all is not supported yet: run one HUNTER_ROLE per container (M1)" and `exit 64`.
2. `docker-compose.yml`: replace the generic `worker` service with `market-worker`: same image/build as `api`, `HUNTER_ROLE=market`, same `env_file`, `depends_on` postgres/redis healthy and `migrate` completed successfully, `restart: unless-stopped`, healthcheck hitting `http://localhost:8001/ready` (reuse the existing `healthcheck.py` pattern if the image has it; look at how the `api` healthcheck is defined and mirror it for port 8001), no host port needed (optionally expose 8001 as `8001:8001` only if `api` does not already publish 8001 — check and avoid a port clash). Keep `api`, `migrate`, `postgres`, `redis`, `web` as they are.
3. `Dockerfile.api-workers`: ensure `services/` is copied before `uv sync --all-packages` (and in any later layer the source is copied), so `python -m hunter_market_worker` resolves inside the image. Keep the image non-root and the layering intact.
4. `docs/DEPLOYMENT.md`: update the compose services table/list to reflect `market-worker` and the one-role-per-container rule.

## Verification (run from the repo root, paste real output)
```
bash -n infra/docker/entrypoint.sh
docker compose -f infra/docker/docker-compose.yml config --services
docker compose -f infra/docker/docker-compose.yml config | grep -A 12 "market-worker:"
docker compose -f infra/docker/docker-compose.yml build api
docker compose -f infra/docker/docker-compose.yml run --rm --no-deps -e HUNTER_ROLE=scanner api ; echo "exit=$?"
```
The last command is expected to fail with a Python "No module named hunter_scanner_worker" style error (honest failure) — paste it. Do NOT start `market-worker` (`up`) yourself; the orchestrator will do that once the worker package lands.

Report: STATUS (DONE/BLOCKED), files modified, real output of every command, deviations.
