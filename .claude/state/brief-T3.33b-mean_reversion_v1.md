# Brief T3.33b — `mean_reversion_v1`: pullback inside a 1 h uptrend (15 m), `research_only`

**Owner:** quant-engineer. **Reviewers:** quant-engineer (cross), `code-reviewer`, Astra.
**Do not commit without the operator's word. Nothing here activates anything and nothing reaches the wallet.**
**Operational rules:** never a background shell; foreground commands with a timeout <= 5 min; the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a`; add exact files only; do not touch `.env*`.
**Discovery, constraints and the shared validation plan:** `.claude/state/notes-T3.33.md`. **Frozen contract:** `.claude/state/exp-drafts/EXP-0009-mean-reversion-pullback-em-tendencia.md`.

---

## 1. What it is, and why it exists

The Lab today only knows how to buy strength: `momentum_v1` buys a breakout, `volume_anomaly_v1`
buys a volume spike. Every loss it measures is therefore confounded with "the market fell". This
version buys **weakness inside strength**: a 15 m close stretched below its own recent mean, while
the 1 h trend is still up.

Family: Connors & Alvarez's RSI(2) mean-reversion (equities, daily), and KB-0002 on intraday
reversion in crypto. Neither was shown on 15 m perpetuals with our costs; the extrapolation is
declared, and the falsification is in the EXP.

## 2. The digest constraint — read this before writing a line

`version_code_ref` freezes a version with its module **plus the transitive closure of the siblings
it imports**. `momentum_v1` and `volume_anomaly_v1` both close over
`{aggregate, base, canonical, envelope, indicators, numeric, schema}`.

**Import them; never edit them.** Editing one re-freezes both live versions and the Lab goes silent
behind a green `/ready`. The z-score helper lives **inside `mean_reversion_v1.py`**.

**Acceptance test (mandatory):** after your change,
`version_code_ref("momentum_v1")` must still be
`hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c`
and `version_code_ref("volume_anomaly_v1")`
`hunter_core.strategies.volume_anomaly_v1@sha256:9b8c14ab3390646ac9adb26fbbb90e160a800f1c70f128d873a49ffd1dd19f22`.

## 3. Identity

```
strategies.key   = "mean_reversion"    # already seeded in infra/scripts/seed_reference.py, status draft
version          = "v1"
registry key     = "mean_reversion_v1"
module           = packages/core/hunter_core/strategies/mean_reversion_v1.py   (<= 350 lines)
timeframe        = Timeframe.M15
direction        = LONG only
purpose          = research_only
```

## 4. The entry rule, exactly

Evaluated at every distinct **15 m** close, in this order.

0. `not ctx.eligible` -> `INELIGIBLE / "ineligible"`.
1. **Signal window (15 m).** `bars_needed = max(zscore_bars, atr_bars_if_same_tf)`; request
   `aggregate(ctx.candles_1m, M15, ctx.source_bar_close, zscore_bars)`. Unavailable ->
   `UNAVAILABLE / window.reason`.
2. **ATR window (15 m).** Same contract as `momentum_v1`: `atr_end = align_open_time(cut, atr_timeframe)`,
   `aggregate(..., atr_bars)`, `wilder_atr(..., atr_period)`, `atr_percent(...)`.
   Unavailable -> `UNAVAILABLE / "atr_" + reason` or `"atr_warmup"`.
3. **Trend gate (1 h).**
   ```
   trend_end   = align_open_time(ctx.source_bar_close, Timeframe.H1)   # the forming hour is excluded
   trend_win   = aggregate(ctx.candles_1m, Timeframe.H1, trend_end, trend_sma_bars + 1)
   sma_1h      = sum(bar.close for bar in trend_win.bars[:-1]) / trend_sma_bars
   ```
   Unavailable -> `UNAVAILABLE / "trend_" + reason`.
   `trend_win.bars[-1].close <= sma_1h` -> `NOT_TRIGGERED / "no_uptrend_1h"` with
   `{"close_1h", "sma_1h"}`.
   The last **complete** hour is the reference; the hour still forming never enters, which is what
   keeps the rule pure under the `source_bar_close` cut.
4. **Stretch (15 m z-score).**
   ```
   closes = [bar.close for bar in bars[-zscore_bars:]]        # INCLUDES the current bar, declared
   mean   = sum(closes) / zscore_bars
   var    = sum((c - mean) ** 2 for c in closes) / zscore_bars     # population variance
   sd     = var.sqrt()                                              # Decimal.sqrt under CONTEXT
   z      = (closes[-1] - mean) / sd
   ```
   `sd == 0` -> `UNAVAILABLE / "zscore_degenerate"`.
   `z > -zscore_depth_min` -> `NOT_TRIGGERED / "not_stretched"` with `{"zscore_15m"}`.
   (The parameter is a **positive depth**: the rule is `z <= -zscore_depth_min`. Spelling it as a
   positive number keeps `constraints.py` able to say `positive` about it without a new rule kind.)
5. **Stabilisation.** `bars[-1].close >= (bars[-1].high + bars[-1].low) / 2`, else
   `NOT_TRIGGERED / "close_below_mid"`. Same convention `volume_anomaly_v1` already uses and that
   has already been reviewed: it refuses a bar that is still falling at its own close.
6. **Cost floor.** `atr_pct_min <= atr_pct <= atr_pct_max`, else `NOT_TRIGGERED / "atr_out_of_range"`.

## 5. Geometry, invalidation, horizon — and the number that chose them

```
reference  = close(t)
stop       = reference - stop_atr   * atr        # 1.0 ATR
target1    = reference + target_atr * atr        # 1.5 ATR
targets_informational = (reference + target2_atr * atr,)     # 2.5 ATR
invalidations = ()                                # NONE, on purpose
horizon_s  = 14400                                # 4 h
```

`not 0 < stop < reference < target1` -> `REJECTED / "geometry"`.

**Why not the "natural" mean-reversion geometry (small target, wide stop).** With the Lab's assumed
costs (`a = 6 bps/side` inside the prices, `f = 4 bps/side` outside), the break-even hit rate of a
stop 1.5 ATR / target 1.0 ATR geometry is **86.7 %** at `atr_pct = 0.003` and **68.0 %** at
`atr_pct = 0.01`. No mean-reversion rule hits that. Inverting to stop 1.0 / target 1.5 and lifting
the ATR% floor to 0.006 puts break-even at **53.4 %**, and at 50.0 % once `atr_pct` reaches 0.008.
Full table in `.claude/state/notes-T3.33.md` §4; it comes from the cost arithmetic, not from a fit.

**Why no invalidation.** This is the native `INV-B` arm of KB-0006: stop, target and horizon are the
only exits. In the 31-day replay of `momentum v2`, 82 of 224 decisions (36.6 %) ended by
invalidation at a mean of −0.6462 R (~−53 R), while the resolved-touch population alone was
+0.115 R per touch. That is **accounting attribution, not a measured effect** — but a mean-reversion
entry, whose whole thesis is that price is *below* where it should be, cannot carry a rule that
exits when price goes lower. Declaring "no invalidation" makes the version falsifiable on its own
terms.

**Horizon 4 h.** A reversion thesis that has not worked in sixteen 15 m bars is wrong. Longer would
also raise the odds of crossing a funding settlement and losing `R_net` coverage (KB-0026).

## 6. Parameters (`default_parameters`, frozen)

| name | default | fragment | description |
|---|---|---|---|
| `trend_timeframe` | `"1h"` | TIMEFRAME | timeframe of the trend gate |
| `trend_sma_bars` | `20` | INTEGER | bars in the trend SMA, current bar excluded |
| `zscore_bars` | `20` | INTEGER | 15 m closes in the z-score, current bar included |
| `zscore_depth_min` | `Decimal("1")` | DECIMAL | how many sd below the mean the close must be (`z <= -this`) |
| `atr_period` | `14` | INTEGER | Wilder ATR period |
| `atr_timeframe` | `"15m"` | TIMEFRAME | timeframe the ATR is computed on |
| `atr_bars` | `97` | INTEGER | bars the ATR is recomputed from (`rolling_window_v1`) |
| `atr_pct_min` | `Decimal("0.006")` | DECIMAL | minimum ATR/close (inclusive) |
| `atr_pct_max` | `Decimal("0.05")` | DECIMAL | maximum ATR/close (inclusive) |
| `stop_atr` | `Decimal("1")` | DECIMAL | stop distance from the reference, in ATR |
| `target_atr` | `Decimal("1.5")` | DECIMAL | target1 distance from the reference, in ATR |
| `target2_atr` | `Decimal("2.5")` | DECIMAL | informational target 2, in ATR |
| `horizon_s` | `14400` | INTEGER | expected holding, seconds |
| `base_confidence` | `Decimal("0.5")` | DECIMAL | uncalibrated constant confidence |
| `assumed_spread_bps` | `Decimal("2")` | DECIMAL | assumed total spread, bps |
| `slippage_bps` | `Decimal("5")` | DECIMAL | assumed slippage per side, bps |
| `fee_bps` | `Decimal("4")` | DECIMAL | assumed fee per side, bps |
| `max_entry_delay_s` | `120` | INTEGER | max seconds from reference close to entry open |

`trend_timeframe` uses the shared `TIMEFRAME_PARAM` fragment (enum `["1m","5m","15m","1h"]`) —
which is why the trend gate is 1 h and **not** 4 h: adding `"4h"` to that enum means editing
`schema.py`, which is inside the frozen closure.

**Declared numeric assumptions:** `zscore_depth_min = 1` and `zscore_bars = 20` are conventional,
not measured. `trend_sma_bars = 20` was picked because 21 hourly bars fit the 26 h context budget
(§7) — a 50-bar hourly trend does **not** fit, and saying so is more honest than picking 50 and
watching every bar come back `warmup`. `atr_pct_min = 0.006` comes from the break-even table (§5).
The day-one replay must publish the distribution of `z` at decision time and the share of bars
refused by each gate, so a later version picks a quantile instead of a convention.

## 7. Window budget — must fit `SHADOW_CONTEXT_MINUTES = 1560`

```
ATR window       97 bars x 15 m                        = 1455 min
trend gate       21 bars x 1 h = 1260 min, ending at align_open_time(cut, 1h),
                 which is up to 45 min before the cut  = 1305 min of reach
z-score window   20 bars x 15 m                        =  300 min
worst case                                               1455 min  <=  1560   OK
```

Assert this in a test with the frozen defaults. Note the second-order cost: the 1 h window needs
1260 **contiguous** minutes, so this version is more gap-sensitive than `momentum_v1` on thin
markets. The day-one replay must report `trend_gap` separately from `gap`.

## 8. `constraints.py` (outside the closure)

```python
"mean_reversion_v1": Constraints(
    positive=frozenset({
        "trend_sma_bars", "zscore_bars", "zscore_depth_min", "atr_period", "atr_bars",
        "atr_pct_max", "stop_atr", "target_atr", "target2_atr", "horizon_s", "max_entry_delay_s",
    }),
    non_negative=frozenset({"atr_pct_min"}) | _COSTS,
    unit_interval=frozenset({"base_confidence"}),
    ordered=(("atr_pct_min", "atr_pct_max"), ("target_atr", "target2_atr")),
),
```

## 9. Envelope (`SupportingFeatures`)

`open_15m`, `high_15m`, `low_15m`, `volume_15m`, `close_15m` (with `source_ts`),
`zscore_15m` (window `zscore_bars`), `sma_15m`, `sd_15m`, `bar_mid_15m`,
`close_1h` (with `source_ts`), `sma_1h` (window `trend_sma_bars`), `atr_pct_15m`,
plus `AtrEvidence` and `assumed_costs(params)`.

Recording `sma_15m` and `sd_15m` next to `zscore_15m` is not redundancy: a z-score alone cannot be
audited after the candles leave retention.

## 10. Tests — synthetic bars, known expected values

In `packages/core/tests/unit/strategies/test_mean_reversion_v1.py`:

The anti-look-ahead suite already exists and is shared: extend
`packages/core/tests/unit/strategies/test_no_lookahead.py` (it already carries
`test_a_cheating_strategy_is_caught_by_the_context`, the deliberate-leak test, and the
decimal-context invariance tests) rather than writing a private copy. Reuse
`strategies/conftest.py` (`BarSpec`, `series`, `minute`, `explode`, `flat`, `D`).

1. **fires** — 21 rising hourly bars, then 20 fifteen-minute bars ending in a dip whose close is
   exactly `mean - 1.2 sd` and above the bar mid; assert direction, reference, stop, target1,
   informational target, `invalidations == ()`, and the reason string.
2. **z-score arithmetic against a hand-computed value:** a series with closes
   `[100]*19 + [97]` — compute mean, population sd and `z` by hand in the test and assert equality
   with `Decimal`, not `pytest.approx`.
3. **does not fire, one branch each:** `no_uptrend_1h`, `not_stretched`, `close_below_mid`,
   `atr_out_of_range`, `ineligible`.
4. **unavailable, one branch each:** `warmup`, `gap`, `trend_warmup`, `trend_gap`, `atr_warmup`,
   `zscore_degenerate` (a flat series).
5. **rejected:** `geometry`.
6. **no look-ahead (mandatory):** the same three mutations as T3.33a — a non-final candle inside the
   window, a final candle closing after `source_bar_close`, and a mutated future candle. The
   `Decision` must be identical in all three, compared on the canonical JSON of the envelope. Extra
   case specific to this version: mutate the **forming hour**'s minutes and assert `sma_1h` and the
   decision do not move.
7. **bootstrap == continuous.**
8. **purity:** two calls, equal decisions; no clock, no IO.
9. **digest isolation:** the two assertions of §2.
10. **constraints:** `check_ranges` refuses `zscore_depth_min = 0`, `stop_atr = 0`, `target_atr = -1`,
    `atr_pct_min > atr_pct_max`, `base_confidence = 42`.
11. **window budget:** §7.

## 11. Files

```
packages/core/hunter_core/strategies/mean_reversion_v1.py            new,  <= 350 lines
packages/core/hunter_core/strategies/registry.py                     +2 lines
packages/core/hunter_core/strategies/constraints.py                  +1 entry
infra/scripts/seed_reference.py                                      description of the `mean_reversion` row
packages/core/tests/unit/strategies/test_mean_reversion_v1.py        new
```

## 12. Proof to paste in the report

```bash
uv run pytest packages/core/tests/unit/strategies/test_mean_reversion_v1.py -q
uv run pytest packages/core/tests/unit/strategies -q -k "strategies or code_ref"
uv run ruff check packages/core/hunter_core/strategies/mean_reversion_v1.py
uv run mypy packages/core/hunter_core/strategies/mean_reversion_v1.py
```

Operator only, on the VPS:

```bash
docker exec -i hunter-api-1 python - mean_reversion v1 --dry-run \
  --changelog 'T3.33b: pullback in a 1h uptrend, research cohort (research_only, no wallet)' \
  < infra/scripts/activate_strategy_version.py
docker exec -i hunter-api-1 python - mean_reversion v1 \
  --changelog 'T3.33b: pullback in a 1h uptrend, research cohort (research_only, no wallet)' \
  < infra/scripts/activate_strategy_version.py
docker exec hunter-strategy-worker-1 python -m hunter_strategy_worker.replay.run \
  --version mean_reversion:v1 --from 2026-08-08 --to 2026-08-23 \
  --markets ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT --workers 3 \
  --cohort replay:<uuid> --ledger /tmp/replay-mean-reversion-v1.jsonl
# second slice 2026-08-23 -> 2026-09-08, SAME cohort
```

Paste the receipt into EXP-0009 and the report. Kill criteria K1–K5: `notes-T3.33.md` §5.1.
For this version specifically, watch K2: a z-score gate at 1 sd fires often, and if the run passes
1 500 decisions the depth is a clock, not a condition.

## 13. Out of scope

Wallet, orders, positions, portfolio PnL, Risk Engine, SHORT, any edit to the seven frozen sibling
modules, any change to `SHADOW_CONTEXT_MINUTES`, and activating anything yourself.
