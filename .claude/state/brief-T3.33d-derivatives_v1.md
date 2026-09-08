# Brief T3.33d — `derivatives_v1`: long after negative funding + price stabilisation (15 m), `research_only`

**Owner:** quant-engineer. **Reviewers:** quant-engineer (cross), `code-reviewer`, Astra.
**Do not commit without the operator's word. Nothing here activates anything and nothing reaches the wallet.**
**Operational rules:** never a background shell; foreground commands with a timeout <= 5 min; the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a`; add exact files only; do not touch `.env*`.
**Discovery, constraints and the shared validation plan:** `.claude/state/notes-T3.33.md`. **Frozen contract:** `.claude/state/exp-drafts/EXP-0011-derivatives-reversao-de-funding.md`.

---

## 1. What it is, and the disagreement with our own knowledge base I am declaring up front

The most repeated claim in crypto: **negative funding = crowded shorts = local bottom**. KB-0023
looked for a test of it with method, sample, period, costs and a control group, and **found none** in
the sources consulted. This version is that test, in the only half that is implementable for us:
long-only, on SPOT paper execution, buying the negative-funding side. The positive-funding half
("sell when funding is extremely positive") is **dropped by construction** — `Decision.direction` is
`Literal[TradeDirection.LONG]`, and Everton's directive is SPOT and long-only.

**KB-0022 recommends not spending a shadow arm on funding.** I am going against it and saying so.
Its recommendation is about funding as a **directional filter bolted onto momentum**, with an
unfavourable prior taken from a study of the **weekly change** of the rate on BTC. This is a
different question: the **level** of the settled rate as a positioning state, with its own price
trigger and its own control group in the replay. If the day-one replay returns fewer than 20
decisions across the four reference markets, the candidate dies there and it will have cost one
replay run — the cheapest falsification in the whole T3.33 set.

## 2. What the engine actually gives you about funding — measured, and it constrains the design

`StrategyContext.funding` is **one `NormalizedFunding` observation**, not a series. There is no
funding history, no baseline, no z-score. `ctx.funding` may be `None`.

In a **replay** — which is the day-one evidence — `ReplayHotState.hgetall` returns `{}`, so
`derivatives._resolve_funding` falls back to the durable `funding_rates` row: a **settled** funding
(`funding_kind = "realized"`, `ts` = the settlement's own instant), up to ~8 h old. That is usable
and it is why this candidate is viable at all.

Two things this rules out, and the module must not pretend otherwise:

- **`index_price` is never populated** on either path (neither `_resolve_funding` branch passes it),
  so `mark - index` — the basis / premium of KB-0021 — is **unreachable from the context**. Do not
  reference it.
- **`ctx.open_interest` is always `None` in a replay** (the durable `ts` is a poll-round bucket that
  can never prove `<= cut`, and the hot state is empty). Do not use OI.

## 3. The digest constraint — read this before writing a line

`version_code_ref` freezes a version with its module **plus the transitive closure of the siblings
it imports**. `momentum_v1` and `volume_anomaly_v1` both close over
`{aggregate, base, canonical, envelope, indicators, numeric, schema}`.

**Import them; never edit them.**

**Acceptance test (mandatory):** after your change,
`version_code_ref("momentum_v1")` must still be
`hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c`
and `version_code_ref("volume_anomaly_v1")`
`hunter_core.strategies.volume_anomaly_v1@sha256:9b8c14ab3390646ac9adb26fbbb90e160a800f1c70f128d873a49ffd1dd19f22`.

## 4. Identity

```
strategies.key   = "derivatives"       # already seeded in infra/scripts/seed_reference.py, status draft
version          = "v1"
registry key     = "derivatives_v1"
module           = packages/core/hunter_core/strategies/derivatives_v1.py   (<= 350 lines)
timeframe        = Timeframe.M15
direction        = LONG only
purpose          = research_only
```

Update the `derivatives` row description in `infra/scripts/seed_reference.py` to what the code does
("Long after a settled negative funding rate and a stabilising 15 m bar."), and do **not** promise
open interest or liquidations in it — this version reads neither.

## 5. The entry rule, exactly

Evaluated at every distinct **15 m** close, in this order.

0. `not ctx.eligible` -> `INELIGIBLE / "ineligible"`.
1. **Funding availability.**
   `ctx.funding is None` -> `UNAVAILABLE / "funding_unavailable"`.
   `(ctx.source_bar_close - ctx.funding.ts).total_seconds() > funding_max_age_s` ->
   `UNAVAILABLE / "funding_stale"` with `{"funding_age_s"}`.
   A stale reading is **unavailable**, never "condition false": a market whose settlements stopped
   arriving proves nothing about the hypothesis and must not re-arm the slot.
2. **Signal window (15 m).** `bars_needed = max(drop_bars + 1, 2)`;
   `aggregate(ctx.candles_1m, M15, ctx.source_bar_close, bars_needed)`.
   Unavailable -> `UNAVAILABLE / window.reason`.
3. **ATR window.** Same contract as `momentum_v1` (`wilder_v1` / `rolling_window_v1`, 14 on 15 m,
   97 bars). Unavailable -> `UNAVAILABLE / "atr_" + reason` or `"atr_warmup"`.
4. **Funding state.** `ctx.funding.funding_rate <= -funding_min_abs`, else
   `NOT_TRIGGERED / "funding_not_negative"` with
   `{"funding_rate", "funding_kind", "funding_age_s"}`.
5. **There must have been a fall.** `change = return_n(bars, drop_bars)`;
   `change > -drop_min_atr * atr_pct` -> `NOT_TRIGGERED / "no_prior_drop"` with
   `{"return_2h", "atr_pct_15m"}`.
   The mechanism is "crowded shorts after a fall". Without the fall it is not the hypothesis, and
   entering anyway would turn the version into "long whenever funding is negative", which is a
   different, weaker claim.
6. **Stabilisation.** `bars[-1].close >= (bars[-1].high + bars[-1].low) / 2`, else
   `NOT_TRIGGERED / "close_below_mid"`. Same reviewed convention as `volume_anomaly_v1`: refuse a
   bar still falling at its own close. This is the difference between "reversal" and "falling knife".
7. **Cost floor.** `atr_pct_min <= atr_pct <= atr_pct_max`, else `NOT_TRIGGERED / "atr_out_of_range"`.

## 6. Geometry, invalidation, horizon

```
reference  = close(t)
stop       = reference - stop_atr   * atr        # 2.0 ATR — wide on purpose
target1    = reference + target_atr * atr        # 3.0 ATR
targets_informational = (reference + target2_atr * atr,)     # 5.0 ATR
invalidations = ()                                # NONE
horizon_s  = 28800                                # 8 h = one funding cycle
```

`not 0 < stop < reference < target1` -> `REJECTED / "geometry"`.

**Why a wide stop.** A squeeze thesis with a tight stop is a noise generator: the entry is taken
right after a fall, in the most volatile part of the move. Break-even hit rate under the Lab's
assumed costs for 2.0 / 3.0 is **46.7 %** at `atr_pct = 0.006` and 44.0 % at 0.01 — versus 72.2 %
for `momentum_v1`'s symmetric 1.5 / 1.5 at its floor. Table in `notes-T3.33.md` §4.

**Why no invalidation.** The thesis is that price is temporarily below where positioning will push
it; a rule that exits when price goes lower contradicts the thesis. Stop, target and horizon are the
whole exit policy, and that makes the version falsifiable on its own terms.

**Declared cost of the 8 h horizon, and it is the main measurement hazard of this candidate.**
An 8 h holding almost always crosses a funding settlement. When the applicable funding cannot be
established, `R_net` is `null` with a reason and `meta.r_ex_funding` is the separate metric with its
own coverage (SHADOW-LAB §3 and §9; KB-0026). Expect materially lower `R_net` coverage than the
other three versions and **report it in every reading**. Kill criterion K5 (`notes-T3.33.md` §5.1)
applies with teeth here.

## 7. Parameters (`default_parameters`, frozen)

| name | default | fragment | description |
|---|---|---|---|
| `funding_min_abs` | `Decimal("0.0001")` | DECIMAL | how negative the settled rate must be: `funding_rate <= -this` |
| `funding_max_age_s` | `32400` | INTEGER | max age of the funding observation at the cut (9 h = one cycle + slack) |
| `drop_bars` | `8` | INTEGER | 15 m bars over which the prior fall is measured (2 h) |
| `drop_min_atr` | `Decimal("1")` | DECIMAL | the fall must be at least this many ATR% (`return <= -this * atr_pct`) |
| `atr_period` | `14` | INTEGER | Wilder ATR period |
| `atr_timeframe` | `"15m"` | TIMEFRAME | timeframe the ATR is computed on |
| `atr_bars` | `97` | INTEGER | bars the ATR is recomputed from (`rolling_window_v1`) |
| `atr_pct_min` | `Decimal("0.006")` | DECIMAL | minimum ATR/close (inclusive) |
| `atr_pct_max` | `Decimal("0.05")` | DECIMAL | maximum ATR/close (inclusive) |
| `stop_atr` | `Decimal("2")` | DECIMAL | stop distance from the reference, in ATR |
| `target_atr` | `Decimal("3")` | DECIMAL | target1 distance from the reference, in ATR |
| `target2_atr` | `Decimal("5")` | DECIMAL | informational target 2, in ATR |
| `horizon_s` | `28800` | INTEGER | expected holding, seconds |
| `base_confidence` | `Decimal("0.4")` | DECIMAL | uncalibrated constant confidence, lower than the price-only versions |
| `assumed_spread_bps` | `Decimal("2")` | DECIMAL | assumed total spread, bps |
| `slippage_bps` | `Decimal("5")` | DECIMAL | assumed slippage per side, bps |
| `fee_bps` | `Decimal("4")` | DECIMAL | assumed fee per side, bps |
| `max_entry_delay_s` | `120` | INTEGER | max seconds from reference close to entry open |

**Declared numeric assumptions, and why `funding_min_abs` is the one number here that is not a
guess:** `0.0001` is `0.01 %`, which is exactly the **interest component** of the Binance funding
formula per 8 h interval (KB-0008). "More negative than the interest component" is therefore a
mechanically meaningful line and not a fitted threshold — a rate below it means the premium
component itself has gone negative. Everything else (`drop_bars = 8`, `drop_min_atr = 1`,
`funding_max_age_s = 32400`) is convention, declared as such.

**What the module must NOT claim.** KB-0023's two structural objections apply and belong in the
docstring: (a) funding is a **bounded** variable — a market at the cap or floor cannot get more
extreme, so the scale saturates exactly where the signal should be strongest; (b) when the settled
rate hits a limit the exchange compresses the interval to 1 h, and **the rate alone does not show
the cadence regime**. This version reads the level only, and says so. The day-one replay must
publish, per decision, `funding_rate`, `funding_kind`, the age of the reading and the distribution
of the rate, so a later version can tell saturation from extremity.

## 8. Window budget — must fit `SHADOW_CONTEXT_MINUTES = 1560`

```
ATR window       97 bars x 15 m = 1455 min
drop window       9 bars x 15 m =  135 min
worst case                        1455 min  <=  1560   OK
```

## 9. `constraints.py` (outside the closure)

```python
"derivatives_v1": Constraints(
    positive=frozenset({
        "funding_min_abs", "funding_max_age_s", "drop_bars", "drop_min_atr",
        "atr_period", "atr_bars", "atr_pct_max",
        "stop_atr", "target_atr", "target2_atr", "horizon_s", "max_entry_delay_s",
    }),
    non_negative=frozenset({"atr_pct_min"}) | _COSTS,
    unit_interval=frozenset({"base_confidence"}),
    ordered=(("atr_pct_min", "atr_pct_max"), ("target_atr", "target2_atr"), ("stop_atr", "target_atr")),
),
```

`funding_min_abs` is declared **positive** because the rule negates it (`<= -funding_min_abs`); a
negative value there would invert the rule silently, which is exactly the class of frozen-cohort
damage `constraints.py` exists to prevent.

## 10. Envelope (`SupportingFeatures`)

`funding_rate`, `funding_kind` (string), `funding_ts` (as `source_ts`), `funding_age_s`,
`mark_price`, `open_15m`, `high_15m`, `low_15m`, `volume_15m`, `close_15m` (with `source_ts`),
`return_2h` (window `drop_bars`), `bar_mid_15m`, `atr_pct_15m`, plus `AtrEvidence` and
`assumed_costs(params)`.

Persisting `funding_kind` and the age is not decoration: KB-0019 showed we could not tell an
estimated reading from a settled one after the fact, and this version's whole claim rests on which
one it saw.

## 11. Tests — synthetic bars, known expected values

In `packages/core/tests/unit/strategies/test_derivatives_v1.py`:

The anti-look-ahead suite already exists and is shared: extend
`packages/core/tests/unit/strategies/test_no_lookahead.py` (it already carries
`test_a_cheating_strategy_is_caught_by_the_context`, the deliberate-leak test, and the
decimal-context invariance tests) rather than writing a private copy. Reuse
`strategies/conftest.py` (`BarSpec`, `series`, `minute`, `explode`, `flat`, `D`).

1. **fires** — a `NormalizedFunding(funding_rate=Decimal("-0.0004"), funding_kind="realized",
   ts=cut - 2h, mark_price=...)`, eight 15 m bars falling 1.5 ATR%, the last one closing above its
   mid; assert direction, reference, stop, target1, informational target, `invalidations == ()` and
   the reason string.
2. **does not fire, one branch each:** `funding_not_negative` (rate `0`, and rate `-0.00005` —
   negative but inside the interest component), `no_prior_drop`, `close_below_mid`,
   `atr_out_of_range`, `ineligible`.
3. **unavailable, one branch each:** `funding_unavailable` (`ctx.funding is None`), `funding_stale`
   (a reading 10 h old), `warmup`, `gap`, `atr_warmup`.
4. **rejected:** `geometry`.
5. **funding cut is honoured:** `build_context` with a funding observation whose `ts` is **after**
   `source_bar_close` must drop it, and the evaluation must be `funding_unavailable` — the
   anti-look-ahead guarantee applied to derivatives, not just to candles.
6. **no look-ahead (mandatory):** the three candle mutations (non-final candle in the window, a final
   candle closing after the cut, a mutated future candle) leave the `Decision` identical, compared
   on the canonical JSON of the envelope. Plus: a **later** funding observation appended to the
   source data must not change the decision.
7. **purity:** two calls, equal decisions; no clock, no IO.
8. **bootstrap == continuous.**
9. **digest isolation:** the two assertions of §3.
10. **constraints:** `check_ranges` refuses `funding_min_abs = -0.0001`, `funding_min_abs = 0`,
    `stop_atr = 0`, `stop_atr >= target_atr`, `atr_pct_min > atr_pct_max`, `base_confidence = 42`.
11. **window budget:** §8.

## 12. Files

```
packages/core/hunter_core/strategies/derivatives_v1.py             new,  <= 350 lines
packages/core/hunter_core/strategies/registry.py                   +2 lines
packages/core/hunter_core/strategies/constraints.py                +1 entry
infra/scripts/seed_reference.py                                    description of the `derivatives` row
packages/core/tests/unit/strategies/test_derivatives_v1.py         new
```

## 13. Proof to paste in the report

```bash
uv run pytest packages/core/tests/unit/strategies/test_derivatives_v1.py -q
uv run pytest packages/core/tests/unit/strategies -q -k "strategies or code_ref"
uv run ruff check packages/core/hunter_core/strategies/derivatives_v1.py
uv run mypy packages/core/hunter_core/strategies/derivatives_v1.py
```

Operator only, on the VPS:

```bash
docker exec -i hunter-api-1 python - derivatives v1 --dry-run \
  --changelog 'T3.33d: negative-funding reversal, research cohort (research_only, no wallet)' \
  < infra/scripts/activate_strategy_version.py
docker exec -i hunter-api-1 python - derivatives v1 \
  --changelog 'T3.33d: negative-funding reversal, research cohort (research_only, no wallet)' \
  < infra/scripts/activate_strategy_version.py
docker exec hunter-strategy-worker-1 python -m hunter_strategy_worker.replay.run \
  --version derivatives:v1 --from 2026-08-08 --to 2026-08-23 \
  --markets ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT --workers 3 \
  --cohort replay:<uuid> --ledger /tmp/replay-derivatives-v1.jsonl
# second slice 2026-08-23 -> 2026-09-08, SAME cohort
```

**Before spending time on the module, run the cheap pre-check** (read-only SQL, operator, VPS):

```sql
-- (1) does the state this version waits for even exist in the window?
-- (2) and does the durable row carry mark_price, which is what makes it usable at all?
SELECT m.symbol,
       count(*)                                        AS settlements,
       count(*) FILTER (WHERE f.rate <= -0.0001)        AS negative_settlements,
       count(*) FILTER (WHERE f.mark_price IS NOT NULL) AS with_mark_price,
       min(f.rate)                                      AS most_negative
FROM funding_rates f JOIN markets m ON m.id = f.market_id
WHERE m.symbol IN ('ETHUSDT','SOLUSDT','XRPUSDT','DOGEUSDT')
  AND f.funding_time >= '2026-08-08' AND f.funding_time < '2026-09-08'
GROUP BY m.symbol ORDER BY 1;
```

Two ways this pre-check kills the candidate before a line of code exists:

- **fewer than ~10 negative settlements in total** across the four markets: the state barely existed
  in the window, K1 will fire, and the module is not worth writing;
- **`with_mark_price` well below `settlements`**: `derivatives._resolve_funding` requires
  `row.mark_price is not None` to use a durable row, and in a replay the hot state is empty — so a
  window of NULL mark prices means `ctx.funding is None` on every bar and the version would answer
  `funding_unavailable` forever. That is a **data bug to report**, not a strategy result.

One query is cheaper than one module. Report its output either way.

Paste the ledger receipt into EXP-0011 and the report, plus the funding coverage table
(`R_net` known / `r_ex_funding` only / neither, with reasons). Kill criteria K1–K5:
`notes-T3.33.md` §5.1.

## 14. Out of scope

Wallet, orders, positions, portfolio PnL, Risk Engine, SHORT, open interest, liquidations,
`index_price`, any edit to the seven frozen sibling modules, any change to
`SHADOW_CONTEXT_MINUTES`, and activating anything yourself.
