# integration

This directory is a placeholder for **M1**: integration tests that cross
service boundaries (e.g. api ↔ execution-worker ↔ exchange sandbox, or
api ↔ market-worker over Redis) do not exist yet, because those services
do not exist yet (docs/ROADMAP.md).

Today, all integration tests live one level down, per app/package, next to
the code they exercise:

- `apps/api/tests/integration/` — the API against a real Postgres and Redis
  (testcontainers), migrated and seeded, with a real signed-and-verified JWT
  (no Clerk credential, no stub principal). Tenant isolation, RBAC, audit,
  auth edge cases, rate limits, WebSocket sessions, webhooks and invitations
  are all covered there, matrix-style where the surface is enumerable (every
  tenant route, every mutating endpoint) so a route added later fails the
  matrix until it is classified.
- `packages/core/tests/integration/` — the schema and repositories against a
  real Postgres.

Content per docs/ARCHITECTURE.md §7; this directory starts holding
cross-service suites once Milestone 1 introduces more than one service to
integrate.
