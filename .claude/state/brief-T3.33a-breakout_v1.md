# Brief T3.33a — `breakout_v1`: volatility-compression breakout (15 m), `research_only`

**Owner:** quant-engineer. **Reviewers:** quant-engineer (cross), `code-reviewer`, Astra.
**Do not commit without the operator's word. Nothing here activates anything and nothing reaches the wallet.**
**Operational rules:** never a background shell; foreground commands with a timeout <= 5 min; the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a`; add exact files only; do not touch `.env*`.
**Discovery, constraints and the shared validation plan:** `.claude/state/notes-T3.33.md`. **Frozen contract:** `.claude/state/exp-drafts/EXP-0008-breakout-compressao-de-volatilidade.md`.

---

## 1. What it is

The one piece of the Weinstein / O'Neil / Minervini family that survives translation to a 15-minute
crypto perpetual: **before the breakout that matters, volatility contracts** (KB-0053). This version
buys a breakout of the previous highs **only when the recent true range is compressed against the
market's own base**, with volume confirmation and a cost floor.

It is deliberately **not** `momentum_v1`. Three differences make the populations different, not
"the same signal with one more filter":

| | `momentum_v1` | `breakout_v1` |
|---|---|---|
| breakout level | max of the previous 20 **closes** | max of the previous 20 **highs** |
| volatility gate | absolute floor only (`atr_pct_min`) | absolute floor **plus** a relative compression ratio |
| geometry | 1.5 / 1.5 ATR (symmetric) | 1.25 / 2.5 ATR (asymmetric) |
| invalidation | close below the breakout level (a few ticks under the entry) | close below the **base low**, with a guard forcing `stop < base_low < reference` |

## 2. The digest constraint — read this before writing a line

`hunter_strategy_worker.code_ref.version_code_ref` freezes a version with the digest of its own
module **plus the transitive closure of the sibling modules it imports**. Measured on this build,
`momentum_v1` and `volume_anomaly_v1` both close over
`{aggregate, base, canonical, envelope, indicators, numeric, schema}`.

**You may import those modules. You may not edit any of them.** Editing one re-freezes both live
versions (including the `paper` line) and the whole Lab goes silent behind a green `/ready`.
Proven both ways in `.claude/state/notes-T3.33.md` §1.1.

Every new helper (the median-true-range ratio, the base low) lives **inside `breakout_v1.py`**.
`registry.py` and `constraints.py` are outside the closure and do take new lines.

**Acceptance test (mandatory):** a test asserting
`version_code_ref("momentum_v1") == "hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c"`
and `version_code_ref("volume_anomaly_v1") == "hunter_core.strategies.volume_anomaly_v1@sha256:9b8c14ab3390646ac9adb26fbbb90e160a800f1c70f128d873a49ffd1dd19f22"`
after your change. If either moves, the change is wrong, not the test.

## 3. Identity

```
strategies.key   = "breakout"          # already seeded in infra/scripts/seed_reference.py, status draft
version          = "v1"
registry key     = "breakout_v1"       # catalogue.registry_key("breakout", "v1")
module           = packages/core/hunter_core/strategies/breakout_v1.py   (<= 350 lines)
timeframe        = Timeframe.M15
direction        = LONG only (Decision.direction is Literal[TradeDirection.LONG]; there is no other option)
purpose          = research_only
```

Update the `breakout` row's `description` in `infra/scripts/seed_reference.py` to match what the code
does ("Breakout of the previous highs after a contraction of true range, confirmed by volume.").
The description is not frozen by the `0002_shadow_lab` trigger; the version's parameters are.

## 4. The entry rule, exactly

Evaluated at every distinct **15 m** close, in this order. The order is part of the contract, and
availability is always `UNAVAILABLE`, never "condition false", so the worker cannot re-arm a market
on a bar it could not evaluate.

0. `not ctx.eligible` -> `INELIGIBLE / "ineligible"`.
1. **Signal window.** `aggregate(ctx.candles_1m, M15, ctx.source_bar_close, bars_needed)` with
   `bars_needed = max(breakout_highs + 1, rvol_window + 1, squeeze_baseline_bars + 2)`
   (the `+2` is the breakout bar `t` plus the extra prior close the first true range needs).
   Unavailable -> `UNAVAILABLE / window.reason`.
2. **ATR window.** `atr_end = align_open_time(ctx.source_bar_close, atr_timeframe)`;
   `aggregate(..., atr_timeframe, atr_end, atr_bars)`; `wilder_atr(bars, atr_period)`;
   `atr_percent(atr, atr_window.bars[-1].close)`. Unavailable -> `UNAVAILABLE / "atr_" + reason` or `"atr_warmup"`.
   Same ATR contract as `momentum_v1` (`wilder_v1` / `rolling_window_v1`, 14 on 15 m, 97 bars) **on purpose**: it is the only way the two populations can be compared on volatility later.
3. **Compression ratio** — the estimator is declared and named, per KB-0053's first instrument decision:

   ```
   estimator = "median_true_range_v1"
   TR_i      = max(high_i - low_i, |high_i - close_{i-1}|, |low_i - close_{i-1}|)     # Wilder's TR
   prior     = bars[:-1]                       # the breakout bar t is EXCLUDED (KB-0053 decision 3)
   trs       = [TR_i for i in prior[1:]]       # needs squeeze_baseline_bars + 1 prior bars
   mtr_long  = median(trs[-squeeze_baseline_bars:])
   mtr_short = median(trs[-squeeze_window_bars:])
   squeeze_ratio = mtr_short / mtr_long
   ```

   `mtr_long <= 0` -> `UNAVAILABLE / "squeeze_baseline_unavailable"`.
   `squeeze_ratio > squeeze_max` -> `NOT_TRIGGERED / "not_compressed"` with `{"squeeze_ratio": ...}`.

   Both windows end at `t-1`. Including the breakout bar would measure the contraction **with** the
   expansion in it and could invert the selection; that is KB-0053's third decision and it is the
   reason this version can be called what it is.
4. **Breakout.** `close(t) > max(high of bars[-breakout_highs-1:-1])`, else
   `NOT_TRIGGERED / "no_breakout"` with `{"close_15m", "max_previous_high_15m"}`.
5. **Volume.** `relative_volume(bars, rvol_window) >= rvol_min`, else `NOT_TRIGGERED / "rvol_low"`.
   `None` -> `UNAVAILABLE / "rvol_unavailable"`.
6. **Cost floor.** `atr_pct_min <= atr_pct <= atr_pct_max`, else `NOT_TRIGGERED / "atr_out_of_range"`.

## 5. Geometry, invalidation, horizon

```
reference  = close(t)
atr        = wilder_atr(...)              # value, not percent
stop       = reference - stop_atr   * atr        # 1.25 ATR
target1    = reference + target_atr * atr        # 2.50 ATR
targets_informational = (reference + target2_atr * atr,)     # 4.0 ATR
base_low   = min(low of bars[-squeeze_window_bars-1:-1])     # the base, breakout bar excluded
invalidations = (Invalidation(kind="close_below", level=base_low, timeframe="15m"),)
horizon_s  = 21600                                            # 6 h
```

**Two geometry guards, both `REJECTED` (never `NOT_TRIGGERED`: the condition held, the decision was
refused, so the market must not re-arm):**

- `not 0 < stop < reference < target1` -> `REJECTED / "geometry"`.
- `not stop < base_low < reference` -> `REJECTED / "geometry_invalidation"`.

The second guard is the whole point of the invalidation design. `momentum_v1`'s invalidation sits a
few ticks below its own entry and, in the 31-day replay of `momentum v2`, 82 of 224 decisions
(36.6 %) ended there at a mean of −0.6462 R, roughly −53 R, while the target/stop population alone
was +0.115 R per resolved touch (`notes-T3.33.md` §4). That is **accounting attribution, not a
measured effect** (KB-0006) — but it is enough to refuse to copy the rule. Here the invalidation is
a **structural** level strictly between the stop and the reference: it can neither be dead code (it
is above the stop) nor a disguised stop (it is below the reference), and the module must say so.

**Report, do not assume:** the day-one replay must publish how often `geometry_invalidation` fires.
If it is more than 20 % of otherwise-triggering bars, the compression window is producing bases that
are wider than the stop and the parameter pair is wrong — which is a **new version**, not a tweak.

## 6. Parameters (`default_parameters`, frozen; nothing hardcoded in the code path)

| name | default | schema fragment | description |
|---|---|---|---|
| `squeeze_window_bars` | `8` | INTEGER | 15 m bars in the short median true range, ending at `t-1` |
| `squeeze_baseline_bars` | `32` | INTEGER | 15 m bars in the baseline median true range, ending at `t-1` |
| `squeeze_max` | `Decimal("0.75")` | DECIMAL | maximum `mtr_short / mtr_long` (inclusive) |
| `breakout_highs` | `20` | INTEGER | previous **highs** the close must clear, current excluded |
| `rvol_window` | `96` | INTEGER | bars in the relative-volume median, current excluded |
| `rvol_min` | `Decimal("1.5")` | DECIMAL | minimum relative volume (inclusive) |
| `atr_period` | `14` | INTEGER | Wilder ATR period |
| `atr_timeframe` | `"15m"` | TIMEFRAME | timeframe the ATR is computed on |
| `atr_bars` | `97` | INTEGER | bars the ATR is recomputed from (`rolling_window_v1`) |
| `atr_pct_min` | `Decimal("0.005")` | DECIMAL | minimum ATR/close (inclusive) |
| `atr_pct_max` | `Decimal("0.05")` | DECIMAL | maximum ATR/close (inclusive) |
| `stop_atr` | `Decimal("1.25")` | DECIMAL | stop distance from the reference, in ATR |
| `target_atr` | `Decimal("2.5")` | DECIMAL | target1 distance from the reference, in ATR |
| `target2_atr` | `Decimal("4")` | DECIMAL | informational target 2, in ATR |
| `horizon_s` | `21600` | INTEGER | expected holding, seconds |
| `base_confidence` | `Decimal("0.5")` | DECIMAL | uncalibrated constant confidence |
| `assumed_spread_bps` | `Decimal("2")` | DECIMAL | assumed total spread, bps |
| `slippage_bps` | `Decimal("5")` | DECIMAL | assumed slippage per side, bps |
| `fee_bps` | `Decimal("4")` | DECIMAL | assumed fee per side, bps |
| `max_entry_delay_s` | `120` | INTEGER | max seconds from reference close to entry open |

**Declared numeric assumptions** (say so in the docstring and in the EXP; none of these is measured):
`squeeze_max = 0.75` and the `8 / 32` window pair are KB-0053's proposed shape with an exploratory
threshold. `atr_pct_min = 0.005` is a compromise between `momentum_v1`'s 0.003 and KB-0008's
0.0089, chosen so the break-even hit rate at the floor is 44.0 % rather than 72.2 % — the number is
in `notes-T3.33.md` §4 and comes from the geometry, not from a fit. The day-one replay **must**
publish the distribution of `squeeze_ratio` over triggering and non-triggering bars so a later
version can pick a quantile instead of a guess.

## 7. Window budget — must fit `SHADOW_CONTEXT_MINUTES = 1560` without touching the knob

```
ATR window            97 bars x 15 m = 1455 min
relative volume       97 bars x 15 m = 1455 min
breakout highs        21 bars x 15 m =  315 min
compression           34 bars x 15 m =  510 min
worst case                             1455 min  <=  1560   OK
```

A test must assert the longest window the strategy can request is `<= 1560` minutes with the frozen
defaults. `aggregate()` requires **every** minute of the window: one missing minute makes the whole
window `gap`, so a longer window costs coverage, not just warm-up.

## 8. `constraints.py` (outside the digest closure — safe to edit)

```python
"breakout_v1": Constraints(
    positive=frozenset({
        "squeeze_window_bars", "squeeze_baseline_bars", "squeeze_max", "breakout_highs",
        "rvol_window", "atr_period", "atr_bars", "atr_pct_max",
        "stop_atr", "target_atr", "target2_atr", "horizon_s", "max_entry_delay_s",
    }),
    non_negative=frozenset({"rvol_min", "atr_pct_min"}) | _COSTS,
    unit_interval=frozenset({"base_confidence"}),
    ordered=(
        ("atr_pct_min", "atr_pct_max"),
        ("squeeze_window_bars", "squeeze_baseline_bars"),
        ("target_atr", "target2_atr"),
    ),
),
```

`_typed_probe` already covers this key: `stop_atr`/`target_atr` are declared, so the dry geometry
probe (close 100, ATR 1) runs and refuses a variant whose geometry never closes.

## 9. Envelope (`SupportingFeatures`)

Every number the decision used, with its window, so the reading can be reproduced after the 1 m
candles leave retention:

`open_15m`, `high_15m`, `low_15m`, `volume_15m`, `close_15m` (with `source_ts`),
`max_previous_high_15m` (window `breakout_highs`), `relative_volume_15m` (window `rvol_window`),
`volume_median_15m`, `mtr_short` (window `squeeze_window_bars`), `mtr_long` (window
`squeeze_baseline_bars`), `squeeze_ratio`, `base_low_15m` (window `squeeze_window_bars`),
`atr_pct_15m`, plus `AtrEvidence` (method, origin, timeframe, period, value, percent, seed,
seed_anchor, bars_used, window_start, window_end) and `assumed_costs(params)`.

## 10. Tests — synthetic bars, known expected values

In `packages/core/tests/unit/strategies/test_breakout_v1.py`:

The anti-look-ahead suite already exists and is shared: extend
`packages/core/tests/unit/strategies/test_no_lookahead.py` (it already carries
`test_a_cheating_strategy_is_caught_by_the_context`, the deliberate-leak test, and the
decimal-context invariance tests) rather than writing a private copy. Reuse
`strategies/conftest.py` (`BarSpec`, `series`, `minute`, `explode`, `flat`, `D`).

1. **fires** — a hand-built series where a 32-bar compressed base is followed by a wide breakout bar
   above the previous 20 highs with 2x median volume; assert direction, `reference_price`, `stop`,
   `target1`, `targets_informational`, the invalidation level and the reason string.
2. **does not fire, one branch each**, asserting the exact `(state, reason)` pair:
   `not_compressed`, `no_breakout`, `rvol_low`, `atr_out_of_range`, `ineligible`.
3. **unavailable, one branch each:** `warmup`, `gap` (one minute removed from the middle of the
   window), `atr_warmup`, `squeeze_baseline_unavailable`, `rvol_unavailable`.
4. **rejected:** `geometry` and `geometry_invalidation` (a base whose low sits below the stop).
5. **no look-ahead (mandatory, and it is the point of the whole design):**
   build the context through `build_context` with (a) a non-final candle inside the window, (b) a
   final candle closing **after** `source_bar_close`, (c) a mutated future candle — the `Decision`
   must be **identical** in all three (compare the canonical JSON of the envelope, not just the
   prices). Then mutate the non-final candle's values and assert the decision still does not move.
6. **bootstrap == continuous:** the same decision from a context built from 1560 minutes read at
   once and from a context built incrementally.
7. **purity:** `evaluate` called twice on the same context returns equal decisions; no clock, no IO
   (assert the module imports nothing from `datetime.now`/`time`/`redis`/`sqlalchemy`).
8. **digest isolation:** the two assertions of §2.
9. **constraints:** `check_ranges` refuses `squeeze_max = 0`, `stop_atr = 0`, `atr_pct_min > atr_pct_max`,
   `base_confidence = 42`, `squeeze_window_bars >= squeeze_baseline_bars`.
10. **window budget:** §7.

## 11. Files

```
packages/core/hunter_core/strategies/breakout_v1.py          new,  <= 350 lines
packages/core/hunter_core/strategies/registry.py             +2 lines (import + DEFAULT_REGISTRY)
packages/core/hunter_core/strategies/constraints.py          +1 entry
infra/scripts/seed_reference.py                              description of the existing `breakout` row
packages/core/tests/unit/strategies/test_breakout_v1.py      new
services/strategy-worker/tests/test_code_ref.py              +1 test (digest isolation), if not already there
```

Commit by exact pathspec, never `git add <dir>`.

## 12. Proof to paste in the report

```bash
uv run pytest packages/core/tests/unit/strategies/test_breakout_v1.py -q
uv run pytest packages/core/tests/unit/strategies -q -k "strategies or code_ref"
uv run ruff check packages/core/hunter_core/strategies/breakout_v1.py
uv run mypy packages/core/hunter_core/strategies/breakout_v1.py
```

Then, **operator only**, on the VPS:

```bash
docker exec -i hunter-api-1 python - breakout v1 --dry-run \
  --changelog 'T3.33a: volatility-compression breakout, research cohort (research_only, no wallet)' \
  < infra/scripts/activate_strategy_version.py
docker exec -i hunter-api-1 python - breakout v1 \
  --changelog 'T3.33a: volatility-compression breakout, research cohort (research_only, no wallet)' \
  < infra/scripts/activate_strategy_version.py
docker exec hunter-strategy-worker-1 python -m hunter_strategy_worker.replay.run \
  --version breakout:v1 --from 2026-08-08 --to 2026-08-23 \
  --markets ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT --workers 3 \
  --cohort replay:<uuid> --ledger /tmp/replay-breakout-v1.jsonl
# second slice 2026-08-23 -> 2026-09-08, SAME cohort
```

Paste the ledger receipt (bars, seconds, bars/s, state counts, signals, outcomes, errors) into
EXP-0008 and into the report. Coverage counts and metrics per SHADOW-LAB §9. The day-one kill
criteria K1–K5 are in `notes-T3.33.md` §5.1 and are frozen **before** the run.

## 13. Out of scope

Wallet, orders, positions, portfolio PnL, Risk Engine, SHORT, any edit to `base.py`,
`aggregate.py`, `indicators.py`, `schema.py`, `envelope.py`, `canonical.py`, `numeric.py`, any
change to `SHADOW_CONTEXT_MINUTES`, and activating anything yourself.
