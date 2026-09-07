# Brief T3.15b — the bridge gate admits `paper` and refuses `live` by name

**Owner:** Sexta-feira on Hermes (first task in the new home), acting as `backend-specialist`; review by `risk-engine-guardian` (role card `.claude/agents/risk-engine-guardian.md`) afterwards. **Do not commit.** **Operational rule: never a background shell; every command in the foreground with a timeout <= 5 min; testcontainers suites one file per pytest invocation; do not touch `.env*`.** Base: `main` at `0db5fbb`.

## Read first
`.claude/state/notes-T3.15.md` (what T3.15 delivered and why the gate was deferred), `packages/core/hunter_core/strategies/envelope.py` (`PURPOSE_RESEARCH_ONLY`, `PURPOSE_PAPER`), `packages/core/hunter_core/admission/sources.py` lines 60-70 and 262-275 (`PURPOSE_LIVE` and the admission gate — the wording to mirror), `services/execution-worker/hunter_execution_worker/bridge_screen.py` lines 55-65 and 215-222, `services/execution-worker/tests/test_bridge_eligibility.py` and `shadow_builders.py` (how signals are built with a purpose), `docs/plans/M3.md` D10 (line 132), `docs/DATABASE.md` §22.

## Deliver
1. `bridge_screen.py`: import `PURPOSE_PAPER` and `PURPOSE_RESEARCH_ONLY` from `hunter_core.strategies.envelope` (one spelling of "paper" in the codebase, not a second literal). Keep `PURPOSE_LIVE = "live"` local (it is refused by name). The gate at line ~219 becomes: `live` -> refuse with reason `live_forbidden` and a message saying "live é Fase 4; ENABLE_LIVE_TRADING=false"; `research_only` -> refuse with reason `research_only` (unchanged); anything else that is not `paper` -> refuse with reason `unknown_purpose`; `paper` -> pass. Update the module docstring and `__all__`.
2. `metrics.py` / wherever the refusal `outcome` label set is declared (T3.14 item 2 — `hunter_bridge_*` counters publish a zero per known reason): add `live_forbidden` and `unknown_purpose` so the counters exist at zero.
3. Tests in `services/execution-worker/tests/test_bridge_eligibility.py`: a `paper` signal passes the door; `research_only` refused as today; `live` refused as `live_forbidden` with the message; an unknown label refused as `unknown_purpose`; every existing test that built signals with `purpose=shadow.PURPOSE_LIVE` to mean "admissible" now uses `PURPOSE_PAPER` (and the one that proves `live` is refused keeps `PURPOSE_LIVE`). `shadow_builders.py`: default purpose of a built signal becomes `PURPOSE_PAPER` only if the builder had `PURPOSE_LIVE` as its default; otherwise leave it.
4. `test_bridge_cycle.py` and `test_bridge_refusal_dedupe.py`: adjust the purpose used for admissible signals the same way; nothing else changes.
5. `docs/PIPELINE.md` §1d/§8 or wherever the bridge is described: one sentence — the bridge admits `purpose = paper` only; `live` refused by name until Phase 4; `research_only` never.

## Prove (paste real output)
```
export PATH="$HOME/.local/bin:/c/Program Files/nodejs:$PATH"
uv run pytest services/execution-worker/tests/test_bridge_eligibility.py -q -p no:randomly
uv run pytest services/execution-worker/tests/test_bridge_cycle.py -q -p no:randomly
uv run pytest services/execution-worker/tests/test_bridge_refusal_dedupe.py -q -p no:randomly
uv run pytest services/execution-worker/tests/test_supervision.py -q -p no:randomly
uv run ruff check services/execution-worker && uv run ruff format --check services/execution-worker
uv run pyright services/execution-worker/hunter_execution_worker
uv run python infra/scripts/check_file_size.py
```
Report in Portuguese, extended format (STATUS · FILES · TESTS with real output · CONCERNS), written to `.claude/state/notes-T3.15b.md` and returned as the final message. Do not commit; the orchestrator commits after review. Nothing is activated by this task: with `ENABLE_PAPER_AUTONOMY=false` the bridge does not consume, and no `paper` version exists in any database.
