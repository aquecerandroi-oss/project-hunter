# Brief T3.15d — the owner DSN lives only where it is used (`DATABASE_URL_MIGRATIONS` off the shared anchor)

**Owner:** devops-engineer (compose). **Reviewer afterwards:** security-reviewer. **Do not commit.** **Operational rule: never a background shell; every command in the foreground with a timeout <= 5 min.** Base: whatever `main` is once T3.0f (`services/market-worker/**`, `infra/docker|vps/**`) has landed — check `git status` on `infra/docker/docker-compose.yml` and `infra/vps/docker-compose.prod.yml` first; if either is still dirty from another agent, wait or re-split this brief again rather than editing under them.

## Source

`.claude/state/review-T3.15-security.md` HIGH 1. This is item 4 of
`.claude/state/brief-T3.15c-purpose-hardening.md`, split off because both
compose files were dirty (T3.0f in flight) when T3.15c ran on 2026-09-08.
Items 1, 2, 3 and 5 of that brief are done — see
`.claude/state/notes-T3.15c.md` for what changed, in particular the new
`0011_strategy_activation_owner` migration that narrows `hunter_worker`'s
grant on `strategy_versions` **assuming the owner DSN itself is the next
thing locked down**, per the security review's framing ("os dois primeiros
HIGH têm de ser fechados antes de derivar/ativar a primeira linha `paper`,
não antes do deploy").

## The finding

`infra/vps/docker-compose.prod.yml:30-33` (and the dev compose,
`infra/docker/docker-compose.yml:15`, if it mirrors) — HIGH — the schema
owner's DSN (`DATABASE_URL_MIGRATIONS`) sits in the `x-prod-db-env` anchor
that `api`, every market-worker shard, `strategy-worker`, `scanner-worker` and
`execution-worker` all inherit. Any one of those containers getting RCE'd
(a dependency CVE, a path traversal reading `/proc/self/environ`, an error
handler that dumps env) can open a connection as the table owner: write
`strategy_versions.purpose = 'paper'`, activate a version outright, or
`ALTER TABLE ... DISABLE ROW LEVEL SECURITY` on any tenant table. §22.3's
"only the activation script, on the migration connection" promise is only as
true as "nothing else has that connection string in its environment" — and
today everything does.

## Deliver

1. Split `x-prod-db-env` into two anchors in `infra/vps/docker-compose.prod.yml`:
   - `x-prod-db-env`: runtime-only (`DATABASE_URL`, `REDIS_URL`, `HUNTER_ENV`,
     whatever else every service already needs) — kept on `api` and every
     worker, unchanged.
   - `x-prod-owner-env`: `DATABASE_URL_MIGRATIONS` only, used **exclusively**
     by the `migrate` service and the new `ops` service (below).
   Mirror the split in `infra/docker/docker-compose.yml` if it carries the
   same anchor for dev/local compose (check first — T3.0f may already have
   changed its shape).
2. Add an `ops` service, **profile-only** (`profiles: ["ops"]` or equivalent —
   it must never start with a bare `docker compose up`), carrying
   `x-prod-owner-env` and whatever image the API/worker already builds (it
   only needs the Python environment, not a running process — `entrypoint: []`
   or a sleep/no-op command is fine, since it exists to be `run --rm`, not
   `up`d). This is where `activate_strategy_version.py`, `open_paper_wallet.py`
   and `request_backfill.py` run from now on:
   `docker compose run --rm ops uv run python infra/scripts/activate_strategy_version.py ...`.
3. Update `docs/DEPLOYMENT.md` with the new invocation for every ops script
   that used to run with a shell that had `DATABASE_URL_MIGRATIONS` in its
   environment directly — say explicitly that after this change, "who can run
   `activate_strategy_version.py`" has an honest answer: whoever has a shell
   on the VPS host with the `.env`, and no container.
4. `docs/DATABASE.md` §22.3/§23: add a line noting the owner DSN's blast
   radius is now `migrate` + `ops` only, not every container — cross-reference
   this brief's commit once it lands.

## Prove

`docker compose -f infra/vps/docker-compose.prod.yml config` parses and shows
`DATABASE_URL_MIGRATIONS` **only** under `migrate` and `ops` (grep the
rendered config, don't eyeball the YAML — an anchor reference is easy to miss
by eye). Same check for the dev compose if touched. No Python/pytest surface
here — this is compose-only, but `infra/scripts/check_file_size.py` and any
`docker compose config` schema validation the repo already runs should still
pass.

Report in Portuguese, extended format; append to or create
`.claude/state/notes-T3.15d.md`.
