# Brief T3.28d — `INTERNAL_PEER_IPS` valida no boot, loga o conjunto e conta os casamentos; workers sem NET_RAW (security-reviewer, T3.28a achados 2–3, LOW)

**Owner:** backend-specialist (com o chapéu de devops para os compose). **Do not commit.** **Operational rule: never a background shell; foreground commands with a timeout <= 5 min; the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a`; add exact files only; do not touch `.env*`; do not stop or recreate local stack containers.** Base: `main` after the T3.28a commit (check `git log -1 -- apps/api/hunter_api/middleware/rate_limit.py`). T3.18c edits `apps/api/hunter_api/{repositories,services,schemas,routers}/lab_*` — disjoint. Your scope: `apps/api/hunter_api/settings.py`, `apps/api/hunter_api/middleware/rate_limit.py`, `apps/api/hunter_api/main.py` (startup log), `apps/api/hunter_api/metrics*.py`, `apps/api/tests/unit/test_rate_limit_internal_peer.py`, `infra/docker/docker-compose.yml`, `infra/vps/docker-compose.prod.yml`, `docs/SECURITY.md`.

## Deliver
1. `internal_peer_ips` validated with `ipaddress.ip_address()` in a `model_validator` — an invalid entry (CIDR, hostname, typo) fails the boot with a clear message.
2. One startup log line `internal_peer_ips_loaded` with the resolved set (no secrets).
3. A counter `hunter_rate_limit_internal_peer_total` incremented when a request is classified as internal peer, so "never matches" is visible on the dashboard.
4. `cap_drop: [NET_RAW, NET_ADMIN]` on every worker service (market/scanner/strategy/execution/analytics, shards, spot) in both compose files — say if any worker needs them (none should); `docs/SECURITY.md` records why (ARP spoof of the fixed `.10`/`.11` addresses from a compromised worker).
5. Tests for 1–3.

## Prove
`ruff`/`pyright`/`check_file_size.py`, per-file tests with real output; `docker compose config` renders both files; report in Portuguese, extended format; `.claude/state/notes-T3.28d.md`.
