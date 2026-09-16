# T4.26b — event ↔ coin matching must look backward (16/09/2026)

Fixes the structural hole KB-0100 measured the same day: `0041`'s per-minute job only scanned events
with `observed_at` in the last 65 min against coins created in the 60 min *after* — a plantão event is
always registered hours after the fact (median 172,8 min that day), so it never fell inside that window.
ARC alone had 60 candidate coins by the job's own rule and matched zero; 874 proposals, 0 with `event_id`.

## What changed

- **Migration `0043_meme_events_scan_cursor`** (`infra/migrations/ddl/meme_event_matches.py` +
  `infra/migrations/versions/0043_meme_events_scan_cursor.py`): a new table `meme_event_matches`
  (`event_id`, `mint`, `match_kind` — `buy`|`avoid`, `matched_at`; PK on `(event_id, mint)`, so
  `ON CONFLICT DO NOTHING` is the whole idempotency story) and a new column
  `meme_events.last_scanned_created_at` (the per-event cursor). `meme_events.mint`/`matched_at` (0041)
  are **legacy** — the job no longer writes them; the CHECK that binds them stays, satisfied because both
  stay `NULL` going forward. Downgrade refuses while any `meme_event_matches` row exists (§17.7 pattern).
  `packages/core/hunter_core/db/models/meme_event_matches.py` (new ORM model) and
  `packages/core/hunter_core/db/models/meme_events.py` (added the cursor field) keep `alembic check`
  green. `packages/core/tests/integration/test_migrations.py`: `HEAD_REVISION` bumped to `0043`,
  `EXECUTABLE_MCAP_REVISION` added (where the `0042` tests now stage), six new `test_0043_*`.

- **The pure matcher moved to a shared package**: `packages/indicators/hunter_indicators/meme/
  event_match.py` (not `hunter_meme_worker` — the audited backfill script needs it too, and
  `infra/scripts/meme_ops_db.py`'s own docstring already states a script must not import another
  service's package for shared logic; a pure gate belongs beside `event_gate.py`/`identity.py`, not in
  either caller's tree). `event_hints()` builds tickers (`symbol_hint` **+** `notes->'tickers'`, `$`
  stripped, uppercased) / keywords (`notes->'keywords'`) / handle (`handle_hint`); `is_match()` is
  symbol-in-tickers **or** name matches a word-boundary regex of tickers∪keywords **or** twitter handle
  equals the event's handle; `event_match_kind()` reads `notes->>'action'` (`avoid` marks every coin the
  event names as a warning, never a buy signal — the "aviso" clone-viveiro event, KB-0100 event 8).
  Unit tests: `packages/indicators/tests/unit/test_meme_event_match.py` (16 cases: symbol/name/handle/
  avoid, `$` stripping, word-boundary — "ARC" never matches "march").

- **`services/meme-worker/hunter_meme_worker/events_repo.py`** rewritten: no more singleton
  `UPDATE meme_events SET mint = …`; instead `_scan_targets` (events inside
  `MEME_EVENT_MATCH_WINDOW_H` hours, default 72) → one `_CANDIDATE_TOKENS` query floored at the earliest
  of every active event's own cursor (`created_at > cursor`, `ix_meme_tokens_created_at`, unchanged since
  0021) → the event × candidate cross product runs in Python (both sides small: a handful of events, a
  slice of a minute of coins) → `INSERT … ON CONFLICT DO NOTHING RETURNING …` per genuine match →
  `UPDATE meme_events SET last_scanned_created_at = :now` for every scanned event, matched or not (the
  cursor always advances, so a quiet tick still shrinks the next one). Same savepoint +
  `statement_timeout = 5000ms` degrade-to-`None` discipline as before (T4.24b's rule).
  `events.py`'s public surface (`events_match_once`, `spawn_events_match`) is unchanged — **no
  `wiring.py`/`main.py` edit was needed**; `main.py` only imports `spawn_events_match` and calls it, and
  that signature never changed.

- **`hunter_indicators.meme.event_gate`**: added `EVENT_AVOID = "event_avoid"` and
  `EventFeatures.match_kind`; `evaluate_event_gate` refuses `event_avoid` outright when
  `match_kind == "avoid"`, before the confirmed/kind check — an avoid-flagged coin is refused whatever its
  `kind`/`confidence` otherwise read. `docs/DATABASE.md` §52.4, `docs/RISK_ENGINE_MEME.md` (a
  cross-reference note above its own admission-checks table, which is a *different* gate —
  `hunter_risk_meme`, execution-level — not the Lab's research gate this task touches).

- **The GateRow/LATERAL wiring**: `proposals_row.GateRow.event_match_kind`,
  `proposals_identity.event_features_of` passes it through, `proposals_reasons.gate_reasons` adds
  `match_kind` to the `event` reasons block. `lab_repo.py`/`lab_repo_fast.py`'s `LEFT JOIN LATERAL` now
  reads `meme_event_matches m JOIN meme_events e ON e.id = m.event_id WHERE m.mint = t.mint ORDER BY
  (m.match_kind = 'avoid') DESC, m.matched_at ASC LIMIT 1` — if a mint has both an `avoid` and a `buy`
  match, the `avoid` one wins the read (the safe choice for a gate that must refuse it).

- **`infra/scripts/meme_event.py`**: `--tickers`/`--keywords`/`--action` (new, merge into `notes` on top
  of `--notes`, backward compatible — `--notes` alone still works exactly as before); `action_unknown`
  refusal. **`rematch` subcommand** split into `infra/scripts/meme_event_rematch.py` (kept `meme_event.py`
  well under 350 lines; same reason the matcher isn't imported from `hunter_meme_worker` — this script
  can't import a service package either) — `rematch --hours 72 [--apply]`, dry-run by default, audits
  `system_events` on apply (`event="rematched"`). Tests: `infra/scripts/tests/test_meme_event.py` (+4:
  `action_unknown`, tickers/keywords/action merge into `notes`, merge on top of hand-written `--notes`),
  `infra/scripts/tests/test_meme_event_rematch.py` (7 new, fake connection, no database).

- **`services/meme-worker/tests/test_events_persistence.py`** rewritten for the new design (Postgres,
  skips without Docker): handle+symbol match, an `avoid` event naming *several* coins (not one — the
  brief's own motivating case), a coin born hours before its event is retroactively registered still
  matches (inside the 30-min grace), an event older than the 72h window is never scanned, a pair stays
  matched across ticks, the cursor prevents a later tick from re-surfacing an already-scanned coin, proposal
  linking, counts, and the `EXPLAIN` of `_CANDIDATE_TOKENS` at 150k `meme_tokens` rows.

- **`hunter_indicators.meme.event_gate`** unit tests extended (`packages/indicators/tests/unit/
  test_meme_event_gate.py`, +4) and `services/meme-worker/tests/test_proposals_identity_event.py` +1
  (`event_avoid` outranks a confirmed, allowed kind end-to-end through `evaluate_gate`).

## EXPLAIN expectation (documented, not re-run with 150k rows in this environment — Docker unreachable)

`_CANDIDATE_TOKENS` (`SELECT mint, symbol, name, twitter, created_at FROM meme_tokens WHERE created_at >
:floor AND created_at <= :now`) is a direct range predicate on `created_at`, the same column
`ix_meme_tokens_created_at` (0021) already indexes — no new index needed. Expected plan: `Index Scan
using ix_meme_tokens_created_at on meme_tokens`, `Index Cond: (created_at > floor AND created_at <=
now)`, never `Seq Scan`. `_SCAN_TARGETS` reads all of `meme_events` inside the 72h window via
`ix_meme_events_observed_at` — a handful of rows a day, cheap regardless of plan shape. The test that
proves this (`test_explain_the_candidate_scan_uses_the_created_at_index_at_100k_rows`) exists and is
correct by construction (same query shape and index the prior EXPLAIN test already proved for `0041`),
but **could not be executed in this session** — Docker Desktop was unreachable (`docker info` failed:
`open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified`). Run it once Docker
is up: `uv run pytest services/meme-worker/tests/test_events_persistence.py -k explain -q` (writes
`.claude/state/notes-T4.26b-explain.txt` itself on success).

## wiring.py — no hook needed

Checked before touching anything: `events.py`'s public surface (`events_match_once`,
`spawn_events_match`) did not change shape, and `main.py` only imports and calls `spawn_events_match` —
no edit to `wiring.py` or `main.py` was required by this task. If a future task wants the new
`events_open`/`events_matched_1h` counts (`events_repo.count_events`, unchanged shape) on the heartbeat,
that hook is in `main.py`/`wiring.py`'s heartbeat assembly, not here.

## Not done / declared cuts

- The actual `notes->>'action' = 'avoid'` marking of today's production event 8 (the clone viveiro) is a
  data-entry action on the VPS (`meme_event.py`, now with `--action avoid`), not code — out of scope for
  an agent that never touches the VPS.
- `pnpm gen:types` not run — no TypeScript touched (`match_kind` label deferred, `docs/DATABASE.md`
  §52.6 already lists it as pending alongside the other T4.26 web labels).
- EXPLAIN not executed live (Docker unreachable this session) — see above.
