# Brief T3.33c — `session_orb_v1`: session opening-range breakout (15 m), `research_only`

**Owner:** quant-engineer. **Reviewers:** quant-engineer (cross), `code-reviewer`, Astra.
**Do not commit without the operator's word. Nothing here activates anything and nothing reaches the wallet.**
**Operational rules:** never a background shell; foreground commands with a timeout <= 5 min; the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a`; add exact files only; do not touch `.env*`.
**Discovery, constraints and the shared validation plan:** `.claude/state/notes-T3.33.md`. **Frozen contract:** `.claude/state/exp-drafts/EXP-0010-session-orb-faixa-de-abertura.md`.

---

## 1. What it is, and the honest caveat first

Opening-range breakout: the first hour of a trading session prints a range, and the rest of the
session tests it. Documented for equity index futures (Crabel; Zarattini & Aziz 2023 on an intraday
S&P momentum rule). **Crypto has no sessions** — it trades 24/7. "Asia / Europe / US" here is *our*
convention, declared in the parameters, and this version exists precisely so that the convention can
be refuted.

It is not a fishing expedition. KB-0032 and KB-0035 already showed that **the clock is sitting
inside our existing thresholds without anyone having decided that** (the ATR% floor behaves as a
time-of-day / regime filter). This version puts the clock in the rule, where it is visible and
falsifiable, instead of leaving it as a side effect.

## 2. The digest constraint — read this before writing a line

`version_code_ref` freezes a version with its module **plus the transitive closure of the siblings
it imports**. `momentum_v1` and `volume_anomaly_v1` both close over
`{aggregate, base, canonical, envelope, indicators, numeric, schema}`.

**Import them; never edit them.** Session resolution lives **inside `session_orb_v1.py`**.

**Acceptance test (mandatory):** after your change,
`version_code_ref("momentum_v1")` must still be
`hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c`
and `version_code_ref("volume_anomaly_v1")`
`hunter_core.strategies.volume_anomaly_v1@sha256:9b8c14ab3390646ac9adb26fbbb90e160a800f1c70f128d873a49ffd1dd19f22`.

## 3. Identity — the only one of the four that needs a new catalogue row

```
strategies.key   = "session_orb"       # NEW row in infra/scripts/seed_reference.py STRATEGIES
version          = "v1"
registry key     = "session_orb_v1"
module           = packages/core/hunter_core/strategies/session_orb_v1.py   (<= 350 lines)
timeframe        = Timeframe.M15
direction        = LONG only
purpose          = research_only
```

Add to `STRATEGIES` in `infra/scripts/seed_reference.py`:

```python
("session_orb", "Session ORB", "trend",
 "Breakout of the opening range of a declared UTC session, confirmed by volume."),
```

`category` is free text (`Mapped[str | None]`), so `"trend"` is a label, not an enum.
`seed_strategies` upserts by key and writes a `draft` `v1`; nothing is activated by seeding.
`infra/scripts/seed.py` must be re-run on the VPS **before** activation, or `activate_strategy_version.py`
will not find the row.

## 4. Purity: the clock is in the context, not in the process

`ctx.source_bar_close` is a UTC datetime carried by the context. Session resolution is a pure
function of it. **`evaluate` still never reads a clock** — this is the one place a reviewer will
want to check twice, so the module must say it out loud and a test must assert it (no import of
`datetime.now`, `time`, `utcnow`).

Sessions, declared in UTC with the Brasilia equivalent in the docstring (D19: no raw enums or
timezone jargon in the product copy; this is code, so both spellings live here):

| session | UTC open | Brasilia (UTC-3) |
|---|---|---|
| asia | 00:00 | 21:00 of the previous day |
| europe | 07:00 | 04:00 |
| us | 13:00 | 10:00 |

```
def _session_open(cut: datetime, hours: tuple[int, int, int]) -> tuple[str, datetime] | None:
    """The latest declared session open at or before `cut`, within the same UTC day
    (the asia open at 00:00 covers the whole day, so there is always one)."""
```

## 5. The entry rule, exactly

Evaluated at every distinct **15 m** close, in this order.

0. `not ctx.eligible` -> `INELIGIBLE / "ineligible"`.
1. **Session position.** Resolve `(session_name, session_open)` from `ctx.source_bar_close`.
   `bars_since_open = (cut - session_open) / 15 min`.
   - `bars_since_open <= range_bars` -> `NOT_TRIGGERED / "inside_opening_range"` (the range is still
     being printed; an observably false condition, so the market may re-arm).
   - `bars_since_open > session_window_bars` -> `NOT_TRIGGERED / "outside_session_window"`.
2. **Window.** `bars_needed = max(bars_since_open, rvol_window + 1)`; `aggregate(ctx.candles_1m, M15,
   ctx.source_bar_close, bars_needed)`. Unavailable -> `UNAVAILABLE / window.reason`.
3. **ATR window.** Same contract as `momentum_v1` (`wilder_v1` / `rolling_window_v1`, 14 on 15 m,
   97 bars). Unavailable -> `UNAVAILABLE / "atr_" + reason` or `"atr_warmup"`.
4. **Opening range.** The first `range_bars` bars of the session inside the window:
   ```
   opening = bars[-bars_since_open : -bars_since_open + range_bars]
   range_high = max(bar.high for bar in opening)
   range_low  = min(bar.low  for bar in opening)
   ```
   `range_high <= range_low` -> `UNAVAILABLE / "degenerate_range"`.
5. **Trigger.** `bars[-1].close > range_high`, else `NOT_TRIGGERED / "no_range_break"` with
   `{"close_15m", "range_high"}`.
6. **Volume.** `relative_volume(bars, rvol_window) >= rvol_min`, else `NOT_TRIGGERED / "rvol_low"`;
   `None` -> `UNAVAILABLE / "rvol_unavailable"`.
7. **Cost floor.** `atr_pct_min <= atr_pct <= atr_pct_max`, else `NOT_TRIGGERED / "atr_out_of_range"`.
8. **Range size guard.** `range_risk_atr = (close - range_low) / atr.value` must satisfy
   `range_risk_atr_min <= range_risk_atr <= range_risk_atr_max`, else
   `REJECTED / "range_geometry"` — `REJECTED`, not `NOT_TRIGGERED`: the break happened, the decision
   was refused, and the market must not re-arm on it.

## 6. Geometry — the stop is a datum, so the target must be in R

```
reference  = close(t)
stop       = range_low                                   # the structure, like volume_anomaly_v1's spike low
risk       = reference - stop
target1    = reference + target_r * risk                 # 2 R nominal at the reference
targets_informational = (reference + target2_r * risk,)  # 4 R
invalidations = ()                                       # NONE: the structure IS the stop
horizon_s  = 14400                                       # 4 h
```

`not 0 < stop < reference < target1` -> `REJECTED / "geometry"`.

**Why the target is in R and not in ATR.** With a data-driven stop, a fixed 2 ATR target makes the
nominal reward-to-risk swing from 4:1 (a 0.5 ATR range) to 1.3:1 (a 2 ATR range) — two strategies
wearing one name. Break-even hit rate under the Lab's assumed costs, measured:

| range risk (ATR) | ATR% | target | break-even hit |
|---:|---:|---|---:|
| 0.5 | 0.006 | fixed 2 ATR | 0.3335 |
| 2.0 | 0.006 | fixed 2 ATR | 0.5834 |
| 0.4 | 0.004 | **2 R** | 0.7504 |
| 1.0 | 0.006 | **2 R** | **0.4446** |
| 1.5 | 0.010 | **2 R** | 0.3778 |

A constant-R target holds break-even between 38 % and 45 % across the allowed band, and the same
table is what fixes `range_risk_atr_min = 1.0`: below that, the 20 bps of assumed cost eat the trade
before the market has an opinion (75 % break-even at a 0.4 ATR range). Full arithmetic in
`.claude/state/notes-T3.33.md` §4.

**Why no invalidation.** The opening-range low *is* the structural level; a separate `close_below`
rule would either sit above the stop (a second, tighter stop nobody declared) or below it (dead
code). `volume_anomaly_v1` already uses this shape and it has been reviewed.

**Declared cost of the 4 h horizon:** it can spill into the next session. That is measured, not
assumed — the day-one replay reports the share of outcomes whose exit falls in a later session.

## 7. Parameters (`default_parameters`, frozen)

| name | default | fragment | description |
|---|---|---|---|
| `session_asia_open_h` | `0` | INTEGER | UTC hour the asia session opens (21:00 Brasilia, previous day) |
| `session_europe_open_h` | `7` | INTEGER | UTC hour the europe session opens (04:00 Brasilia) |
| `session_us_open_h` | `13` | INTEGER | UTC hour the us session opens (10:00 Brasilia) |
| `range_bars` | `4` | INTEGER | 15 m bars that form the opening range (1 h) |
| `session_window_bars` | `20` | INTEGER | how many bars past the session open a break still counts (5 h) |
| `rvol_window` | `96` | INTEGER | bars in the relative-volume median, current excluded |
| `rvol_min` | `Decimal("1.3")` | DECIMAL | minimum relative volume (inclusive) |
| `atr_period` | `14` | INTEGER | Wilder ATR period |
| `atr_timeframe` | `"15m"` | TIMEFRAME | timeframe the ATR is computed on |
| `atr_bars` | `97` | INTEGER | bars the ATR is recomputed from (`rolling_window_v1`) |
| `atr_pct_min` | `Decimal("0.006")` | DECIMAL | minimum ATR/close (inclusive) |
| `atr_pct_max` | `Decimal("0.05")` | DECIMAL | maximum ATR/close (inclusive) |
| `range_risk_atr_min` | `Decimal("1")` | DECIMAL | minimum `(close - range_low) / ATR` (inclusive) |
| `range_risk_atr_max` | `Decimal("2.5")` | DECIMAL | maximum `(close - range_low) / ATR` (inclusive) |
| `target_r` | `Decimal("2")` | DECIMAL | target1 in nominal R of the range risk |
| `target2_r` | `Decimal("4")` | DECIMAL | informational target 2, in nominal R |
| `horizon_s` | `14400` | INTEGER | expected holding, seconds |
| `base_confidence` | `Decimal("0.5")` | DECIMAL | uncalibrated constant confidence |
| `assumed_spread_bps` | `Decimal("2")` | DECIMAL | assumed total spread, bps |
| `slippage_bps` | `Decimal("5")` | DECIMAL | assumed slippage per side, bps |
| `fee_bps` | `Decimal("4")` | DECIMAL | assumed fee per side, bps |
| `max_entry_delay_s` | `120` | INTEGER | max seconds from reference close to entry open |

Three scalar hour parameters rather than a list: `canonical.py` does serialise lists, but three
integers keep `constraints.py` and the frozen schema trivial to audit, and a future version that
prefers a list is free to be a different version.

**Declared numeric assumptions:** the three session hours are the conventional crypto-desk split and
are **not** measured; `range_bars = 4` (one hour) is Crabel's shape, not a fit; `session_window_bars
= 20` bounds the session to five hours so the three sessions do not overlap in the rule;
`rvol_min = 1.3` is deliberately looser than `momentum_v1`'s 1.5 because a session open already
carries a volume seasonal. `range_risk_atr_min = 1.0` comes from the break-even table (§6).
The day-one replay must publish decisions **per session** — if one session carries all of them, the
"session" hypothesis is really a single-hour hypothesis and must be re-stated as one.

## 8. Window budget — must fit `SHADOW_CONTEXT_MINUTES = 1560`

```
ATR window            97 bars x 15 m                 = 1455 min
relative volume       97 bars x 15 m                 = 1455 min
session span          <= session_window_bars + 1 = 21 bars x 15 m = 315 min
worst case                                            1455 min  <=  1560   OK
```

Assert with the frozen defaults. Note `session_window_bars <= 24` is a hard requirement of the
budget and of the non-overlap of the three sessions; put it in `constraints.py` (§9).

## 9. `constraints.py` — needs one new rule kind

The three hour parameters need a **bounded** range (`0 <= h <= 23`); `Constraints` has no such rule
today. Add it — `constraints.py` is outside the digest closure, so this is safe:

```python
@dataclass(frozen=True, slots=True)
class Constraints:
    ...
    bounded: tuple[tuple[str, Decimal, Decimal], ...] = ()
    """Inclusive ``(name, low, high)`` ranges the strategy's own arithmetic requires
    (a UTC hour outside 0..23 is not a threshold, it is a version that never fires)."""
```

and in `_table_rules`, after `unit_interval`:

```python
for name, low, high in rules.bounded:
    value = _number(params.get(name))
    if value is not None and not low <= value <= high:
        problems.append(f"{name}={value} está fora de [{low}, {high}]")
```

Then:

```python
"session_orb_v1": Constraints(
    positive=frozenset({
        "range_bars", "session_window_bars", "rvol_window", "atr_period", "atr_bars",
        "atr_pct_max", "range_risk_atr_min", "range_risk_atr_max", "target_r", "target2_r",
        "horizon_s", "max_entry_delay_s",
    }),
    non_negative=frozenset({
        "session_asia_open_h", "session_europe_open_h", "session_us_open_h",
        "rvol_min", "atr_pct_min",
    }) | _COSTS,
    unit_interval=frozenset({"base_confidence"}),
    bounded=(
        ("session_asia_open_h", Decimal(0), Decimal(23)),
        ("session_europe_open_h", Decimal(0), Decimal(23)),
        ("session_us_open_h", Decimal(0), Decimal(23)),
        ("session_window_bars", Decimal(1), Decimal(24)),
    ),
    ordered=(
        ("atr_pct_min", "atr_pct_max"),
        ("range_risk_atr_min", "range_risk_atr_max"),
        ("target_r", "target2_r"),
        ("session_asia_open_h", "session_europe_open_h"),
        ("session_europe_open_h", "session_us_open_h"),
        ("range_bars", "session_window_bars"),
    ),
),
```

`_typed_probe`'s geometry probe does **not** apply here (there is no `stop_atr`), exactly as it
already does not apply to `volume_anomaly_v1`. Do not fake one.

## 10. Envelope (`SupportingFeatures`)

`session` (string: `"asia"|"europe"|"us"`), `session_open` (as `source_ts`), `bars_since_open`,
`range_high`, `range_low`, `range_risk_atr`, `open_15m`, `high_15m`, `low_15m`, `volume_15m`,
`close_15m` (with `source_ts`), `relative_volume_15m` (window `rvol_window`), `volume_median_15m`,
`atr_pct_15m`, plus `AtrEvidence` and `assumed_costs(params)`.

`session` as a `FeatureEvidence` with a **string** value is legal (`value: Decimal | int | str | None`).

## 11. Tests — synthetic bars, known expected values

In `packages/core/tests/unit/strategies/test_session_orb_v1.py`:

The anti-look-ahead suite already exists and is shared: extend
`packages/core/tests/unit/strategies/test_no_lookahead.py` (it already carries
`test_a_cheating_strategy_is_caught_by_the_context`, the deliberate-leak test, and the
decimal-context invariance tests) rather than writing a private copy. Reuse
`strategies/conftest.py` (`BarSpec`, `series`, `minute`, `explode`, `flat`, `D`).

1. **fires** — a session open at 13:00 UTC, four bars printing a range, then a bar at 14:15 UTC
   closing above `range_high` with 1.5x median volume; assert the session name, `range_high`,
   `range_low`, `stop == range_low`, `target1 == close + 2*(close - range_low)`,
   `invalidations == ()` and the reason string.
2. **session boundary table** — parametrised over `source_bar_close` at 00:00, 06:45, 07:00, 12:45,
   13:00, 23:45 UTC; assert the resolved session and open. Include the 00:00 case explicitly (the
   asia open is also a day boundary).
3. **does not fire, one branch each:** `inside_opening_range`, `outside_session_window`,
   `no_range_break`, `rvol_low`, `atr_out_of_range`, `ineligible`.
4. **unavailable, one branch each:** `warmup`, `gap`, `atr_warmup`, `degenerate_range`,
   `rvol_unavailable`.
5. **rejected:** `range_geometry` (a range narrower than 1 ATR **and** one wider than 2.5 ATR) and
   `geometry`.
6. **no look-ahead (mandatory):** the three mutations (non-final candle in the window, a final candle
   closing after `source_bar_close`, a mutated future candle) leave the `Decision` identical,
   compared on the canonical JSON of the envelope.
7. **purity, and the clock specifically:** two calls give equal decisions; the module imports no
   clock (`datetime.now`, `time`, `utcnow`) and no IO; a test that monkeypatches the system clock
   forward by a day and asserts the decision is unchanged.
8. **bootstrap == continuous.**
9. **digest isolation:** the two assertions of §2.
10. **constraints:** `check_ranges` refuses `session_us_open_h = 24`, `session_europe_open_h = -1`,
    `session_window_bars = 48`, `range_risk_atr_min >= range_risk_atr_max`, `target_r = 0`,
    `base_confidence = 42`, and asia >= europe >= us out of order.
11. **window budget:** §8.

## 12. Files

```
packages/core/hunter_core/strategies/session_orb_v1.py           new,  <= 350 lines
packages/core/hunter_core/strategies/registry.py                 +2 lines
packages/core/hunter_core/strategies/constraints.py              +1 rule kind (`bounded`) +1 entry
infra/scripts/seed_reference.py                                  +1 STRATEGIES row (`session_orb`)
packages/core/tests/unit/strategies/test_session_orb_v1.py       new
packages/core/tests/unit/strategies/test_constraints.py            +tests for the `bounded` rule
```

## 13. Proof to paste in the report

```bash
uv run pytest packages/core/tests/unit/strategies/test_session_orb_v1.py -q
uv run pytest packages/core/tests/unit/strategies -q -k "strategies or constraints or code_ref"
uv run ruff check packages/core/hunter_core/strategies/session_orb_v1.py
uv run mypy packages/core/hunter_core/strategies/session_orb_v1.py
```

Operator only, on the VPS — **the seed comes first here**, because the family is new:

```bash
docker exec -i hunter-api-1 python - < infra/scripts/seed.py
docker exec -i hunter-api-1 python - session_orb v1 --dry-run \
  --changelog 'T3.33c: session opening-range breakout, research cohort (research_only, no wallet)' \
  < infra/scripts/activate_strategy_version.py
docker exec -i hunter-api-1 python - session_orb v1 \
  --changelog 'T3.33c: session opening-range breakout, research cohort (research_only, no wallet)' \
  < infra/scripts/activate_strategy_version.py
docker exec hunter-strategy-worker-1 python -m hunter_strategy_worker.replay.run \
  --version session_orb:v1 --from 2026-08-08 --to 2026-08-23 \
  --markets ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT --workers 3 \
  --cohort replay:<uuid> --ledger /tmp/replay-session-orb-v1.jsonl
# second slice 2026-08-23 -> 2026-09-08, SAME cohort
```

Paste the receipt into EXP-0010 and the report, **with the per-session breakdown**. Kill criteria
K1–K5: `notes-T3.33.md` §5.1, plus one specific to this version: if a single session carries more
than 70 % of the decisions, the hypothesis must be re-stated as a single-hour hypothesis before any
further evaluation.

## 14. Out of scope

Wallet, orders, positions, portfolio PnL, Risk Engine, SHORT, any edit to the seven frozen sibling
modules, any change to `SHADOW_CONTEXT_MINUTES`, and activating anything yourself.
