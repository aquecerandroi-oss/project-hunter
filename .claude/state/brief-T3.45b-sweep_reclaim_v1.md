# Brief T3.45b — `sweep_reclaim_v1`: a swept swing low that closes back above it (15 m), `research_only`

**Owner:** quant-engineer. **Reviewers:** `code-reviewer`, `risk-engine-guardian`, Astra.
**Do not commit without the operator's word. Nothing here activates anything and nothing reaches the wallet.**
**Operational rules:** never a background shell; foreground commands with a timeout <= 5 min; the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a`; add exact files only; do not touch `.env*`, `apps/**`, `services/**` (except reading), `obsidian/**`.
**Frozen contract:** `.claude/state/exp-drafts/EXP-0017-sweep-reclaim.md` (hypothesis and protocol are frozen there; this brief may not change a single number of them).
**Pre-check that authorised this brief:** `infra/scripts/sql/research/2026-09-09-sweep-reclaim-precheck.sql`, run 2026-09-08 21:59:07Z. Discovery notes: `.claude/state/notes-T3.45.md`. Shared validation plan: `.claude/state/notes-T3.33.md` §5.1.

---

## 1. What it is, and why it exists

A 15 m bar whose **low pierces** a confirmed swing low of the last 40 bars by at least 0,25 ATR and
whose **close comes back above** that low, on above-median volume. Long. The stop is the pierced
low; the target is 2 R.

Why this one, and why now: it was the **first substitute** on the T3.33 shortlist (#9), it took the
slot that `derivatives_v1` left when its own pre-check killed it, and it is the only candidate whose
**stop comes from the data** and whose cost gate is therefore expressible on the quantity that
actually appears in the toll identity (`custo_R = 0,0020 / risco%`) instead of on ATR%, which is a
proxy. `momentum v5` (T3.40) tried to buy a toll cap with `atr_pct_min = 0,020` and produced **zero**
decisions; this version buys it with `risk_pct_min = 0,006` and the pre-check measured that the
population survives.

**Read this before you budget your day.** The pre-check measured **57 events in 31 days × 4 markets,
on 17 distinct calendar days** (43 after a lower-bound estimate of the slot re-arm barrier). K1
(< 20 decisions) is survived by 2,85×, **not** with room to spare, and the maturity ruler (100
evaluable **and** 30 distinct days) is **unreachable in the replay by construction**. The day-one
replay exists to answer K1/K2/K4/K6 and the geometry guard — not to conclude anything. Write the
module knowing that.

## 2. The digest constraint — read this before writing a line

`hunter_strategy_worker.code_ref.version_code_ref` freezes a version with its module **plus the
transitive closure of the siblings it imports**. Import the siblings; **never edit them**. Editing
one re-freezes every live version and the Lab goes silent behind a green `/ready`.

Import exactly the closure `mean_reversion_v1` uses: `aggregate`, `base`, `envelope`, `indicators`,
`numeric`, `schema` (and `hunter_core.domain.*`). **Do not import `tl_pivots`/`tl_scan`/`tl_lines`** —
that is `trendline_breakout_v1`'s closure, and joining it means any future trend-line fix re-freezes
this version too. **The pivot detector for this version lives inside `sweep_reclaim_v1.py`.**

**Acceptance test (mandatory).** After your change, all six of these must be byte-identical to what
they are today (measured 2026-09-08 on `main`):

```
momentum_v1           = hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c
volume_anomaly_v1     = hunter_core.strategies.volume_anomaly_v1@sha256:9b8c14ab3390646ac9adb26fbbb90e160a800f1c70f128d873a49ffd1dd19f22
breakout_v1           = hunter_core.strategies.breakout_v1@sha256:4c920b0cc412429c2c4a6a19ca389aca8a215a638f0ff750a8caf61b16264ff1
mean_reversion_v1     = hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f
session_orb_v1        = hunter_core.strategies.session_orb_v1@sha256:a4d514adeb0771d5ae23303878fb4fdac734721d6ac0140801c88d617e878bba
trendline_breakout_v1 = hunter_core.strategies.trendline_breakout_v1@sha256:659087e19daa6f8d5bc71f4c64d47ea4026f720bcd1576d8a0b620b448aef449
```

`registry.py` and `constraints.py` are **outside** the closure and may receive new lines.

## 3. Identity — a new catalogue row

```
strategies.key   = "sweep_reclaim"      # NEW row in infra/scripts/seed_reference.py STRATEGIES
version          = "v1"
registry key     = "sweep_reclaim_v1"
module           = packages/core/hunter_core/strategies/sweep_reclaim_v1.py   (<= 350 lines)
timeframe        = Timeframe.M15
direction        = LONG only
purpose          = research_only
```

Add to `STRATEGIES` in `infra/scripts/seed_reference.py`:

```python
(
    "sweep_reclaim",
    "Sweep and Reclaim",
    "reversion",
    "Long a bar that pierces a confirmed swing low and closes back above it, on above-median volume.",
),
```

`category` is free text (`Mapped[str | None]`). `seed_strategies` upserts by key and writes a
`draft` `v1`; **seeding activates nothing**. `infra/scripts/seed.py` must be re-run on the VPS
**before** activation, or `activate_strategy_version.py` will not find the row. No
`opportunity_weights` change: those are scorer components, not strategy families.

## 4. The entry rule, exactly

Evaluated at every distinct **15 m** close, in this order. **The order is part of the contract** and
the reason vocabulary below is frozen. Unavailability is **never** reported as a false condition —
the worker must not re-arm a market on a bar it could not evaluate.

0. `not ctx.eligible` -> `INELIGIBLE / "ineligible"` with `{"eligibility_reason": ...}`.
1. **Signal window (15 m).** `signal_bars = max(pivot_lookback_bars + pivot_k + 1, rvol_window + 1)`
   = `max(44, 21)` = 44 with the frozen defaults. Compute it from the parameters, never hardcode 44.
   `aggregate(ctx.candles_1m, M15, ctx.source_bar_close, signal_bars)`; unavailable ->
   `UNAVAILABLE / window.reason` with `window.detail`.
2. **ATR window (15 m).** Same contract as the other three: `atr_end = align_open_time(cut, atr_timeframe)`,
   `aggregate(..., atr_bars)`, `wilder_atr(..., atr_period)`, `atr_percent(...)`.
   Unavailable -> `UNAVAILABLE / "atr_" + reason`; not warmed up -> `UNAVAILABLE / "atr_warmup"`.
   **This single reading is the scale for everything**: prominence, sweep depth, stop buffer and
   `risk_atr` (declared divergence from `patterns/pivots.py`, EXP-0017 Protocol).
3. **Pivot.** Over the signal window, with the current bar at index `t = len(bars) - 1`, a bar `i` is
   a **confirmed swing low** when:
   - `pivot_k <= i <= t - pivot_k` (the right-hand side is the whole point: a pivot is only *known*
     `k` bars later, and a pivot at `t-1` or `t-2` **does not exist yet**);
   - `i >= t - pivot_lookback_bars`;
   - `bars[i].low < bars[j].low` for the `k` bars to the **left**, and
     `bars[i].low <= bars[j].low` for the `k` bars to the **right** (ties go to the older bar, T3.34
     rule 3);
   - prominence `= min(max(high of the k left), max(high of the k right)) - bars[i].low`, and
     `prominence / atr.value >= min_swing_atr`. The pivot bar's own range is **excluded** from the
     shoulders (T3.34 rule 2 — including it made prominence ~1 ATR by construction and the filter
     filtered nothing).

   Take the **most recent** `i` that qualifies. None -> `NOT_TRIGGERED / "no_pivot"` with
   `{"lookback_bars": ...}`.
4. **Sweep.** `bars[t].low <= pivot_low - sweep_atr * atr.value`; otherwise
   `NOT_TRIGGERED / "no_sweep"` with `{"low_15m", "pivot_low", "sweep_atr_observed"}`.
5. **Reclaim.** `bars[t].close > pivot_low` (strict); otherwise `NOT_TRIGGERED / "no_reclaim"` with
   `{"close_15m", "pivot_low"}`.
6. **Volume.** `rvol = relative_volume(bars, rvol_window)` (the shared helper: last bar's volume over
   the **median** of the `rvol_window` bars before it). `None` -> `UNAVAILABLE / "rvol_unavailable"`
   (incomplete lookback or a zero median — a market that did not trade has no baseline, and that is
   not a false condition). `rvol < rvol_min` -> `NOT_TRIGGERED / "low_rvol"` with `{"rvol_15m"}`.
7. **Cost floor.** `stop = bars[t].low - stop_buffer_atr * atr.value`;
   `risk = close - stop`; `risk_pct = risk / close`. If `risk_pct < risk_pct_min` ->
   `NOT_TRIGGERED / "risk_below_floor"` with `{"risk_pct", "toll_cap_r"}` where
   `toll_cap_r = Decimal("0.0020") / risk_pct` — publish the toll of the bar we refused, because
   that is the number the next version will argue with.
8. **Risk cap.** `risk_atr = risk / atr.value`. If `risk_atr > risk_atr_max` ->
   `NOT_TRIGGERED / "risk_above_cap"` with `{"risk_atr"}`.
9. **Geometry guard.** `target1 = close + target_r * risk`,
   informational `close + target2_r * risk`. If **not** `0 < stop < close < target1` ->
   `REJECTED / "geometry"` with `{"stop", "reference_price", "target1"}`.
   This branch is the one that killed `breakout_v1` (14/14, notes-T3.33e). Here it is structurally
   unreachable — `stop < low <= close` always, and `stop > 0` unless `stop_buffer_atr * atr >= low`,
   which needs an ATR of the order of the price. **Keep the guard anyway** and let the day-one
   replay report `REJECTED / geometry` as a count: a guard that can never fire is cheap; a geometry
   that fires unnoticed cost us a whole candidate.
10. Otherwise `TRIGGERED / "signal"`.

## 5. Geometry, invalidation, horizon

```
stop      = low_t - stop_buffer_atr * ATR            # the swept low, plus a buffer
risk      = close_t - stop
target1   = close_t + target_r  * risk               # 2 R
target2   = close_t + target2_r * risk               # 3 R, informational only
invalidations = ()                                   # ARGUED, not forgotten
horizon_s = 14400                                    # 4 h = 16 decision bars
```

**The target is in R, not in ATR**, and that is the frozen lesson of `session_orb_v1`
(notes-T3.33 §4 item 3): with a stop given by the data, a fixed ATR target is two strategies wearing
one name.

**`invalidations = ()` is a decision.** The swept low *is* the structure and it is already the stop;
a rule that exits above the stop is a second, tighter stop with no thesis of its own — the design
that cost `momentum v2` about **−53 R over 82 decisions**. This makes the version the third `INV-B`
arm of the Lab. C8 of the review gate scores it 10/`fail`; the divergence is declared in EXP-0017
and **must not be "fixed" in code**.

**Break-even at the frozen cost floor** (`risco% = 0,600 %`, `a = 6 bps/side` inside prices,
`f = 4 bps/side` outside): `R_net` at target `1,5133`, at stop `−1,2112`, **break-even 44,46 %**,
**toll cap 0,3333 R**. Reproduce it in `Decimal` in a test (§10.12) — it is the arithmetic that chose
`target_r = 2`.

## 6. Parameters (`default_parameters`, frozen — 20 keys)

```python
default_parameters: Mapping[str, Any] = {
    "pivot_k": 3,
    "min_swing_atr": Decimal("1"),
    "pivot_lookback_bars": 40,
    "sweep_atr": Decimal("0.25"),
    "rvol_window": 20,
    "rvol_min": Decimal("1.5"),
    "atr_period": 14,
    "atr_timeframe": Timeframe.M15.value,
    "atr_bars": 97,
    "stop_buffer_atr": Decimal("0.1"),
    "risk_pct_min": Decimal("0.006"),
    "risk_atr_max": Decimal("3"),
    "target_r": Decimal("2"),
    "target2_r": Decimal("3"),
    "horizon_s": 14400,
    "base_confidence": Decimal("0.5"),
    "assumed_spread_bps": Decimal("2"),
    "slippage_bps": Decimal("5"),
    "fee_bps": Decimal("4"),
    "max_entry_delay_s": 120,
}
```

`parameters_schema = schema_of({...})` with one line per key, `INTEGER_PARAM` / `DECIMAL_PARAM` /
`TIMEFRAME_PARAM` as in `mean_reversion_v1`. **No `atr_pct_min` and no `atr_pct_max`** — deliberate;
the reason and the measurement are in EXP-0017. Twenty keys: the decision timeframe is the class
attribute `Strategy.timeframe`, and `signal_bars` is **derived**, not a parameter — deriving it is
what keeps `pivot_lookback_bars` and the window in sync when a variant moves the lookback.

## 7. Window budget — must fit `SHADOW_CONTEXT_MINUTES = 1560`

```
ATR window     97 bars x 15 m                     = 1455 min
signal window  44 bars x 15 m                     =  660 min
worst case                                          1455 min  <=  1560   OK
```

Assert it in a test with the frozen defaults. Second-order cost, the same one `momentum_v1` pays:
`aggregate()` needs **all 1455 minutes** contiguous, so one missing minute makes the whole window
`gap`. What the pre-check actually measured, and it is better news than expected: of 2961 fifteen-
minute bars per market, **exactly 96 have no ATR — the warm-up, and nothing else**. Zero windows
were lost to interior gaps in all four markets (the 15 bars missing from the 31 days sit at one
edge, not scattered). So `gap`/`atr_gap` should be **near zero** in the replay; report them
separately anyway (K4 is at 40 %), and if they are not near zero, the difference between
`aggregate()` and this SQL is a finding that has to be named, not smoothed over.

## 8. `constraints.py` (outside the closure)

Add to `constraints_table.py`:

```python
"sweep_reclaim_v1": Constraints(
    positive=frozenset({
        "pivot_k", "min_swing_atr", "pivot_lookback_bars", "sweep_atr", "rvol_window",
        "atr_period", "atr_bars", "stop_buffer_atr", "risk_pct_min", "risk_atr_max",
        "target_r", "target2_r", "horizon_s", "max_entry_delay_s",
    }),
    non_negative=frozenset({"rvol_min"}) | _COSTS,
    unit_interval=frozenset({"base_confidence"}),
    bounded=(
        ("pivot_k", Decimal(1), Decimal(10)),
        ("risk_pct_min", Decimal("0.0001"), Decimal("0.15")),
    ),
    ordered=(("target_r", "target2_r"),),
),
```

Two notes for the reviewer. `stop_buffer_atr` is in `positive` on purpose: a zero buffer puts the
stop on the exact tick that the thesis says gets swept. `risk_pct_min` has an **upper** bound of
0,15 because it is also the version's `stop_loss_pct` axis, and C5 of the review gate fails above
0,15 — a variant that types `risk_pct_min = 0.5` would be a strategy that never trades and that no
risk profile would size.

## 9. Envelope (`SupportingFeatures`)

`open_15m`, `high_15m`, `low_15m`, `volume_15m`, `close_15m` (with `source_ts`),
`pivot_low` (with `source_ts` = the pivot bar's `open_time`), `pivot_index_back` (`t - i`, so the
age of the structure is auditable), `pivot_prominence_atr`, `sweep_depth_atr`
(`(pivot_low - low_t)/ATR`), `rvol_15m` (window `rvol_window`), `risk_pct`, `risk_atr`,
`toll_cap_r`, plus `AtrEvidence` (method, origin, timeframe, period, value, percent, seed,
seed_anchor, bars_used, window_start, window_end) and `assumed_costs(params)`.

`pivot_low` **and** its age and prominence, not just `pivot_low`: after the candles leave retention,
a level with no provenance cannot be audited, and "which swing low was that?" is the first question
anyone will ask of a decision that lost.

## 10. Tests — synthetic bars, known expected values

In `packages/core/tests/unit/strategies/test_sweep_reclaim_v1.py`. Reuse
`strategies/conftest.py` (`BarSpec`, `series`, `minute`, `explode`, `flat`, `D`). Extend the shared
`test_no_lookahead.py` rather than writing a private copy.

1. **fires** — a hand-built series: a swing low at `i`, three bars each side confirming it, then a
   bar at `t` whose low is exactly `pivot_low - 0,3 ATR` and whose close is above `pivot_low`, with
   volume 2× the median. Assert direction, `reference_price`, `stop`, `target1`, informational
   target, `invalidations == ()`, and the reason string.
2. **the geometry, by hand:** with `ATR = 1`, `close = 100`, `low = 98`, `stop_buffer_atr = 0.1`:
   `stop = 97.9`, `risk = 2.1`, `target1 = 104.2`, `target2 = 106.3`, `risk_atr = 2.1`,
   `risk_pct = 0.021`. Assert with `Decimal` equality, never `pytest.approx`.
3. **the pivot rules, one test each:** ties go to the older bar (a plateau of equal lows yields one
   pivot, the first); a wiggle whose prominence is `< 1 ATR` is not a pivot; the shoulders exclude
   the pivot bar's own range.
4. **THE anti-look-ahead test of this version (mandatory):** a bar at `t-2` that *would* be a swing
   low if the two bars after it existed **must not** be used — assert `no_pivot`, then append two
   bars so it becomes `t-4`, and assert it *is* used. This is the confirmation window, and it is the
   only place in this module where a leak could hide.
5. **does not fire, one branch each:** `no_pivot`, `no_sweep`, `no_reclaim` (close exactly *at*
   `pivot_low` — the comparison is strict), `low_rvol`, `risk_below_floor`, `risk_above_cap`,
   `ineligible`.
6. **unavailable, one branch each:** `warmup`, `gap`, `atr_warmup`, `atr_gap`, `rvol_unavailable`
   (zero median).
7. **rejected:** `geometry`, forced with an absurd `stop_buffer_atr` via params.
8. **no look-ahead (mandatory, the shared three mutations):** a non-final candle inside the window, a
   final candle closing after `source_bar_close`, and a mutated future candle. The `Decision` must be
   **identical** in all three, compared on the canonical JSON of the envelope.
9. **bootstrap == continuous**; **purity** (two calls, equal decisions, no clock, no IO).
10. **digest isolation:** the six assertions of §2.
11. **constraints:** `check_ranges` refuses `pivot_k = 0`, `sweep_atr = -0.1`, `stop_buffer_atr = 0`,
    `risk_pct_min = 0`, `risk_pct_min = 0.5`, `target_r > target2_r`, `base_confidence = 42`.
12. **the break-even arithmetic** of §5 in `Decimal`: `1.5133 / -1.2112 / 0.4446 / 0.3333` at
    `risco% = 0,006`, to four places.
13. **window budget:** §7.

## 11. Files

```
packages/core/hunter_core/strategies/sweep_reclaim_v1.py            new,  <= 350 lines
packages/core/hunter_core/strategies/registry.py                    +2 lines (import + roster)
packages/core/hunter_core/strategies/constraints_table.py           +1 entry
infra/scripts/seed_reference.py                                     +1 STRATEGIES row
packages/core/tests/unit/strategies/test_sweep_reclaim_v1.py        new
packages/core/tests/unit/strategies/test_no_lookahead.py            +1 case (the k-confirmation one)
```

Nothing else. In particular: none of the seven closure siblings, no `schema.py`, no
`SHADOW_CONTEXT_MINUTES`, no `apps/**`, no `services/**`.

## 12. Proof to paste in the report

```bash
uv run pytest packages/core/tests/unit/strategies/test_sweep_reclaim_v1.py -q
uv run pytest packages/core/tests/unit/strategies services/strategy-worker/tests/test_code_ref.py -q
uv run ruff check packages/core/hunter_core/strategies/sweep_reclaim_v1.py
uv run mypy packages/core/hunter_core/strategies/sweep_reclaim_v1.py
uv run python -c "from hunter_strategy_worker.code_ref import version_code_ref; \
  [print(k, version_code_ref(k)) for k in ('momentum_v1','volume_anomaly_v1','breakout_v1', \
   'mean_reversion_v1','session_orb_v1','trendline_breakout_v1','sweep_reclaim_v1')]"
```

Operator only, on the VPS, **and only after `seed.py` has run**:

```bash
# 0. the CLI has been broken in a published image before (T3.40 CONCERN 2) — check first
docker exec hunter-strategy-worker-1 python -m hunter_strategy_worker.replay.run --help

# 1. dry run: it must print the sweep_reclaim_v1 digest, and it must match §12 above
docker exec -i hunter-api-1 python - sweep_reclaim v1 --dry-run \
  --changelog 'T3.45b: swept swing low reclaimed, research cohort (research_only, no wallet)' \
  < infra/scripts/activate_strategy_version.py

# 2. activation (irreversible: it freezes code_ref)
docker exec -i hunter-api-1 python - sweep_reclaim v1 \
  --changelog 'T3.45b: swept swing low reclaimed, research cohort (research_only, no wallet)' \
  < infra/scripts/activate_strategy_version.py

# 3. replay, two contiguous slices, SAME cohort
docker exec hunter-strategy-worker-1 python -m hunter_strategy_worker.replay.run \
  --version sweep_reclaim:v1 --from 2026-08-08 --to 2026-08-23 \
  --markets ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT --workers 3 \
  --cohort replay:<uuid> --ledger /tmp/replay-sweep-reclaim-v1.jsonl
# second slice 2026-08-23 -> 2026-09-08, SAME cohort
```

**What the day one must report, and the numbers to compare against.** The pre-check is the
prediction; the replay is the check of the module against it. Publish this table:

| quantity | pre-check (SQL, 2026-09-08) | replay | verdict |
|---|---:|---|---|
| decisions | 57 (43 after the re-arm barrier, lower bound) | ? | a replay far below 43 means the module is stricter than the SQL and **why** must be named |
| distinct days | 17 | ? | maturity (30) is unreachable — say so |
| markets | 4, max share 29,8 % (XRPUSDT) | ? | K6 at 60 % |
| `REJECTED / geometry` | expected 0 | ? | > 20 % of triggering bars kills the geometry (the `breakout_v1` criterion) |
| `unavailable` | 96 bars/market = **3,2 %**, all of it warm-up; **zero** interior gaps | ? | K4 at 40 %; a large `gap` count means the engine and this SQL disagree, and that is the finding |

Kill criteria K1–K6 in EXP-0017; the day-one evaluation must also carry the decomposition by **BTC
regime** and by **ATR% decile** (that is what makes C4 = 80 true rather than promised), the
pre-registered control group (**swept, did NOT reclaim, with RVOL — 732 bars in the pre-check**), and
the `(market, bar)` intersection with the `mean_reversion_v1` cohort (the overlap objection that
T3.33 raised against this candidate in the first place).

## 13. Out of scope

Wallet, orders, positions, portfolio PnL, Risk Engine, SHORT, the 2-bar sweep variant, any edit to
the closure siblings, any change to `SHADOW_CONTEXT_MINUTES`, lowering `risk_pct_min` (that is a new
EXP with its own gate — EXP-0017 registers the refusal in writing), and activating anything yourself.
