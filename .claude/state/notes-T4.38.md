# T4.38 — triage of the red tests before the deploy

## 1. `test_lab_operator_3.py` — two tests, `KeyError: 'operator/4'`

Cause: `0039_meme_creator_repeat` (T4.24) retired `operator/4` and seeded
`operator/5`; the test still hardcoded `OPERATOR_4_ID` and the label
`"operator/4"`.

Fix (test-only, already on disk): renamed `OPERATOR_4_ID` → `OPERATOR_5_ID`
(`01994d00-6c1a-7000-8000-000000000011`), and — per the brief — the desk
operator is now read dynamically instead of a hardcoded label:

```python
operator = next(s for s in specs.values() if s.kind == "operator" and s.name == "operator")
```

so the next retirement (`operator/6`, …) won't need this test touched again.
Both renamed tests (`..._hands_the_desk_to_operator_5_...`,
`test_operator_5_proposes_...`) pass.

## 2. `test_lab_lines.py::test_a_probe_scales_once_when_the_line_is_born_and_sells_when_it_breaks`

Two independent causes, both fixed test-side:

- `pedigree_exclusions` is on by default (T4.16/EXP-M6): an unknown
  creator/symbol refuses every proposal by name before the gate is read.
  `_plant_curve` didn't set `creator`/`symbol`, so it collided with the
  pedigree gate. Fix: pass `creator=f"C_{mint}", symbol=mint` (unique per
  test run).
- `hype_probe_v0/2` (0030, EXP-M5 arm 2 — same numbers plus one flow
  condition) is active alongside the set under test and independently
  satisfies the same curve, so `bets`/`meme_proposals` legitimately carry
  a second, sibling probe/scale pair on the same mint. Fix: every lookup
  (`scale = next(...)`, the pending-proposal count) is now pinned to
  `rule_set_id == HYPE_PROBE_ID`. Not a production bug — the comparison
  arm doing its job.

`test_lab_persistence.py`'s `_plant_curve` gained the matching
`creator`/`symbol` optional kwargs (default `None`, so every caller that
doesn't exercise the pedigree gate is unaffected).

## 3. `packages/core/tests/integration/test_migrations.py::test_0043_a_pair_matched_once_stays_matched` — TEARDOWN FK violation (NOT edited — brief forbids it)

Reproduced in isolation:
`asyncpg.exceptions.ForeignKeyViolationError: update or delete on table
"meme_events" violates foreign key constraint
"fk_meme_event_matches_event_id_meme_events" on table "meme_event_matches"`.

Cause: the test's `finally` block (around line 8251) deletes the parent
row first, then relies on `_CLEAN_0043` to delete the child rows:

```python
    finally:
        asyncio.run(
            _write(upgraded, [("DELETE FROM meme_events WHERE id = :id", {"id": event_id})])
        )
        asyncio.run(_write(upgraded, list(_CLEAN_0043)))
```

`_CLEAN_0043`'s first statement is `DELETE FROM meme_event_matches WHERE
mint LIKE 'X43_%'` — i.e. the child (`meme_event_matches`, holding
`event_id` → this test's own `X43_PAIR` match, still present because the
test's first insert succeeded) is deleted *after* the attempt to delete
the parent `meme_events` row, so the parent delete fails on the FK and the
whole teardown aborts.

`test_0043_refuses_a_downgrade_while_a_match_exists` (same file, a few
tests below) already gets this right — it deletes
`meme_event_matches WHERE event_id = :id` explicitly before deleting
`meme_events`. `test_0043_check_refuses_an_unknown_match_kind` gets away
with the same order only because its insert into `meme_event_matches`
never committed (it raises inside the CHECK constraint).

**Exact fix to apply in `test_0043_a_pair_matched_once_stays_matched`'s
`finally` block** (swap the two statements — run `_CLEAN_0043` first, then
the now-redundant/harmless single-row delete by id):

```python
    finally:
        asyncio.run(_write(upgraded, list(_CLEAN_0043)))
        asyncio.run(
            _write(upgraded, [("DELETE FROM meme_events WHERE id = :id", {"id": event_id})])
        )
```

(`_CLEAN_0043`'s second statement, `DELETE FROM meme_events WHERE title
LIKE 'T4.26b test%'`, already deletes this test's event by title, so the
explicit by-id delete afterward is a no-op safety net, not a duplicate
failure.)

Not run as part of this task's required suites (`packages/core/tests/unit`
only) — confirmed failing before the fix, fix not applied by me because
editing `test_migrations.py` is out of scope for T4.38.

Addendum: the file already carries this exact fix, uncommitted, on disk
(pre-dating this session — a prior agent's in-flight edit, also bumping
`HEAD_REVISION` to `0047_meme_bonding_curve_raw` for T4.39's migration and
applying the identical `_CLEAN_0043`-before-`DELETE meme_events` swap to
`test_0043_check_refuses_an_unknown_match_kind`'s `finally` block too, by
the same reasoning). Left untouched and unstaged, per the brief — not part
of this commit.

## 4. `test_events_persistence.py::test_a_pair_matched_once_stays_matched_across_ticks`

Cause: cross-test collision inside the same file — both this test and
`test_a_handle_match_and_a_symbol_match_both_name_their_mint` used the
symbol `"BUM"`, and the whole file runs against one shared,
session-scoped database (`conftest.py`'s `migrated_db_url` is never reset
between tests). The other test's `"BUM"`-symbol event, still inside the
72h scan window, cross-matched this test's own `"BUM"` mint, naming two
events for one pair instead of one.

Fix (test-only): renamed this test's token/event symbol from `"BUM"` to
`"ONCE"` (mint stays `T426B_ONCE`) — no longer collides with any other
symbol in the file.

## 5. `test_persistence.py::test_retention_prunes_only_what_aged_out_and_needs_the_marker` — cross-test pollution via a real production bug

T4.35 saw this fail only in full-suite runs. Root cause: `T426B_RETRO`
(planted by `test_events_persistence.py::test_a_coin_born_hours_before_a_retroactively_registered_event_still_matches`,
`created_at` 2026-09-16 — older than this test's `cutoff` of 2026-10-01)
gets matched to an event via `meme_event_matches`. `0043` gave
`meme_event_matches.mint` a real FK to `meme_tokens` (unlike every
bet/proposal, which keep `mint` as bare text on purpose so an aged-out
coin can still be pruned). Without a guard, `prune_tokens`'s single
batched `DELETE` hit the FK violation on `T426B_RETRO` and aborted the
**whole** batch — not just that row — so `OLD_MINT` (this test's own
subject) survived pruning it should not have, in a full-suite run where
both files share the database.

This is a real production bug, not just test pollution: any coin that
once triggered a plantão event would permanently jam retention behind it
in production too, forever.

**Production fix applied** (`services/meme-worker/hunter_meme_worker/repo.py`,
`_PRUNE_TOKENS`): excluded matched mints from the batch instead of letting
the FK violation abort it —

```sql
AND NOT EXISTS (SELECT 1 FROM meme_event_matches m WHERE m.mint = t.mint)
```

— the same exclusion pattern already used for a pinned mint. A new test,
`test_persistence.py::test_retention_skips_a_mint_still_matched_to_an_event_instead_of_aborting_the_batch`,
reproduces the failure scenario directly (raw SQL, so it doesn't depend on
T4.39's in-flight `TokenRow`/`upsert_token` columns) and asserts the
matched mint is skipped while a plain aged-out mint next to it is still
pruned. This fix also resolves the original cross-test pollution: the
batch no longer aborts on `T426B_RETRO`, so `OLD_MINT` is pruned as
expected even in a full-suite run.

## Suite results

- `uv run pytest services/meme-worker/tests -q -m "not live"` → **421
  passed** in 659.37s (0:10:59), exit code 0. No failures caused by
  T4.39/T4.41's in-flight files at the time of this run.
- `uv run pytest packages/indicators/tests packages/core/tests/unit -q -m
  "not live"` → **2732 passed** in 89.74s (0:01:29), exit code 0.
- `packages/core/tests/integration/test_migrations.py::test_0043_a_pair_matched_once_stays_matched`
  reproduced failing (FK violation in teardown, see §3) — out of scope to
  fix here; exact fix documented above for whoever owns that file next.

## Gates on my 5 files

- `uv run ruff check <5 files>` → All checks passed.
- `uv run ruff format --check <5 files>` → 5 files already formatted.
- `uv run pyright <5 files>` → 2 pre-existing errors in
  `test_lab_persistence.py` (`_FakeChainOneRead`/`_FakeChainRefuses` at
  lines ~806/857 missing the `commitment` kwarg `ChainSource.get_curve_states`
  now requires). Confirmed identical in `HEAD` (`b1dc5d15`, T4.43) before
  any of today's edits — pre-existing, unrelated to this task's diff and
  to T4.39/T4.41's uncommitted files (`context.py` is untouched in the
  working tree). Not fixed here: out of scope for T4.38's brief, and the
  fix belongs with whoever owns `ChainSource`/the fast lane's fakes.
