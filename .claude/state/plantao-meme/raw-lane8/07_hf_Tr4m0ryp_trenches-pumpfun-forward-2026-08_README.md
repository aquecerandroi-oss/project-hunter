---
license: other
license_name: polyform-noncommercial-1.0.0
license_link: https://polyformproject.org/licenses/noncommercial/1.0.0/
task_categories:
  - tabular-classification
  - time-series-forecasting
language:
  - en
tags:
  - solana
  - blockchain
  - defi
  - memecoin
  - pump-fun
  - bonding-curve
  - point-in-time
  - leakage
  - market-microstructure
  - tabular
  - finance
size_categories:
  - 100K<n<1M
pretty_name: Trenches pump.fun Forward Capture 2026-08
configs:
  - config_name: observations
    data_files: observations.parquet
  - config_name: features
    data_files: features.parquet
  - config_name: labels
    data_files: labels.parquet
  - config_name: truth_set
    data_files: truth_set.parquet
---

# Trenches pump.fun Forward Capture, 2026-08

A point-in-time observational dataset of Solana bonding-curve token launches.
730,850 observations over 85,442 mints across 4 venues, captured live from
2026-08-06T22:40:47Z to 2026-08-13T01:07:50Z at a 75.0 s poll cadence, with
**a derivability timestamp per field block on every row**.

That last property is the point of the dataset. Most financial tabular releases
carry one timestamp per row and leave the reader to argue about whether a
feature was knowable at decision time. Here each field block carries its own
`tau__` stamp in epoch milliseconds, so leakage is a quantity you compute
rather than a claim you make. The dataset ships with a worked example of the
stamps catching a real leak: the post-reach block passes an as-stamped replay
and fails an honest audit, because it resolves a median 20.52 s after the
instant it is stamped with.

Total download: 104,654,533 bytes (99.8 MB) across 13 files, of which
104,580,833 bytes (99.7 MB) are the 9 data files.

## Files

| File | Rows | Columns | Bytes |
| --- | --- | --- | --- |
| `observations.parquet` | 730,850 | 124 | 46,320,372 |
| `curve_paths.jsonl.gz` | 1,361 mints, 289,952 events | nested | 20,025,085 |
| `features.parquet` | 85,442 | 103 | 11,502,368 |
| `launch_windows.jsonl.gz` | 999 mints, 52,389 events | nested | 10,359,921 |
| `post_ids.csv` | 59,915 | 3 | 4,729,263 |
| `split.json` | 85,442 mints | 3 partitions | 4,439,538 |
| `labels.parquet` | 84,584 | 17 | 3,795,182 |
| `account_state.jsonl.gz` | 84,584 | 9 | 2,956,239 |
| `truth_set.parquet` | 3,676 | 19 | 452,865 |
| `MANIFEST.json` | 9 entries | n/a | 17,633 |
| `DATASHEET.md` | n/a | n/a | 30,639 |
| `README.md` | n/a | n/a | 13,741 |
| `dataset-metadata.json` | n/a | n/a | 11,687 |

`MANIFEST.json` carries a SHA-256, a row count, a column count and a source
attribution for every file. `DATASHEET.md` is the full datasheet, following
Gebru et al. (2021).

## Quick start

```python
import pandas as pd

features = pd.read_parquet("features.parquet")     # 85,442 rows, 103 columns
labels = pd.read_parquet("labels.parquet")         # 84,584 rows, 17 columns
panel = features.merge(labels[["mint", "path_completed", "n_obs", "segment"]],
                       on="mint", how="inner")     # 84,584 rows

import json
split = json.load(open("split.json"))
train = panel[panel["mint"].isin(set(split["in_sample"]))]      # 50,812 pump.fun mints
test = panel[panel["mint"].isin(set(split["out_of_sample"]))]   # 30,059 pump.fun mints

print(panel["path_completed"].mean())   # 0.011350, that is 1.135%
```

Loading through `datasets`:

```python
from datasets import load_dataset

observations = load_dataset("Tr4m0ryp/trenches-pumpfun-forward-2026-08", "observations", split="train")
print(observations.num_rows)            # 730850
```

The point-in-time panel is the larger file and rewards column pruning:

```python
import pyarrow.parquet as pq

table = pq.read_table("observations.parquet",
                      columns=["mint", "seen_at_ms", "gate_inputs__holder_count",
                               "tau__gate_inputs", "tau__reach", "tau__reach_read"])
print(table.num_rows)                   # 730850
```

## What is in each file

**`observations.parquet`** is the instrument record: one row per poll per
token, 730,850 rows. Column families are `gate_inputs__*` (24 vendor screen
numerics), `vendor_audit__*` (12 vendor audit numerics), `verdict__*` and
`gate__<name>__ran` / `__passed` (the live screen's decision over 6 gates),
`reach__*` (35 dehydrated X columns), `fold__*` (10 chain aggregates), 7 chain
scalars, and 10 `tau__` stamps.

**`features.parquet`** is the modelling panel: one row per mint at first
sighting, 85,442 rows and 103 columns, with curve-progress proxies excluded.

**`labels.parquet`** carries the outcome per pump.fun mint, 84,584 rows. Use
`path_completed` (960 true, 1.135%), the chain reading. `graduated` (880 true)
is the live resolver's independent call. **`y_theta_70` is degenerate in this
release and is false on every row**; see the limitations below.

**`split.json`** is a forward-only time split at 2026-08-08T21:38:15Z with a
10,800 s embargo: 51,311 mints in sample, 30,359 out of sample, 3,772
embargoed. It holds mint addresses, not row indices. No shuffling. Seed
20260814.

**`account_state.jsonl.gz`** is the terminal read of every pump.fun bonding
curve account, 84,584 records, 960 with the completion flag set. It is the
source of `path_completed`, published so the label is checkable.

**`curve_paths.jsonl.gz`** and **`launch_windows.jsonl.gz`** are decoded
per-trade chain data: 342,341 priced bonding-curve events with slot, block
time, transaction index, signed SOL and token amounts, post-trade virtual and
real reserves, and the trading wallet. They cover 2026-05-08T22:33:37Z to
2026-06-10T17:41:33Z and **do not join to the capture**: the intersection with
the 85,442 captured mints is 0 mints.

**`truth_set.parquet`** is 3,676 mints entered by tracked traders, with an
adjudicated boolean outcome (304 true, 8.27%) and a generated English
rationale. All 3,676 are present in the capture.

**`post_ids.csv`** is the dehydrated X layer: 59,915 rows of
`mint,post_id,seen_at_ms` over 20,495 distinct post identifiers.

## What is withheld

**Post content is not published.** Redistributing tweet text breaches X's
developer terms, so this is a dehydrated release: `text`, `author_handle`,
`author_description`, `conversation_id` and `author_id` are removed, and so
are the vendor's copies of the token's social links (`twitter`,
`twitter_handle`, `website`, `telegram`). Derived numerics are kept, because a
count is a measurement rather than content: view, like, reply, retweet, quote
and bookmark counts, follower and following counts, account age in seconds,
post character count, and the verified, blue-verified, default-profile,
default-avatar and protected flags.

To rehydrate, take `post_ids.csv` and call `GET /2/tweets?ids=<up to 100 ids>`
with a bearer token. Posts deleted since 2026-08 will not return.

**The raw vendor payload is withheld pending terms review.** Each captured row
held the vendor's API response verbatim, 133 keys. Republishing a commercial
API response wholesale is a question this project has not answered, so the
whole block is excluded. What is published instead are the 36 numeric fields
the study actually consumed, as `gate_inputs__*` and `vendor_audit__*`.
`features.parquet` is derived from exactly those.

**Chain data is published in full.** Curve paths, launch windows, account
state, completion labels and split indices are decoded public Solana state and
carry no restriction.

No credentials, keys or keyed endpoint URLs appear anywhere. Endpoint names
only. The bundle is scanned before release by `src/release/secretscan.py`,
which reads decoded columns rather than compressed bytes.

## Limitations you must read before using this

**The base rate is a property of the instrument, not of the market.** The
completion rate here is 1.135% (960 of 84,584 mints). The historical
832,941-launch corpus for the same venue runs at 0.198%. The vendor feed is
weighted toward launches already near completion, so this dataset is roughly
five times enriched. Report every rate against 1.07%, never against 0.198%,
and state which population you mean.

**There is a 69.09-hour gap, and it is not random with respect to time of
day.** Observations stop at 2026-08-10T00:37:48Z and resume at
2026-08-12T21:43:12Z. A second gap of 2.09 hours follows on 2026-08-12. The
capture spans 146.45 hours and observes 75.27 of them. Because the gap is an
outage rather than a sample, it removes the same clock positions on three
consecutive days. Every mint carries a `segment` column, `pre_gap` or
`post_gap`, and every result should state which side it was measured on.

**Chain state covers pump.fun only, 84,584 of 85,442 mints.** The other 858
mints launched on `ray_launchpad` (394), `meteora_dbc` (277) and `sugar` (187)
and have vendor and reach data but no outcome. Do not pool venues in a rate.

**The terminal label has precision 1.000 and recall 0.917, and recall falls
with observation count.** Judging the live resolver against the chain reading
over 84,584 mints: 880 true positives, 0 false positives, 80 false negatives.
Recall by number of looks is 0.9686 at 1 look, 0.9658 at 2, 0.9630 at 3 to 4,
0.9321 at 5 to 9, and 0.8333 at 10 or more. The resolver fires on absence from
the feed, so a mint that lingered is the one it is slowest to catch. Prefer
`path_completed`, and stratify by `n_obs`.

**`y_theta_70` is unusable.** The per-trade curve-path pull for this
population exhausted its RPC budget at 0.0 coverage, so `path_status` reads
`error:not_pulled` on all 84,584 rows, `max_progress_path` is null throughout,
and the peak-progress label is false everywhere. It is kept in the schema so
the failure is visible rather than silently dropped.

**The reach block is not derivable at first sighting.** Over the 56,593 reach
blocks present at first sighting, the corrected read stamp lands a median
20.52 s after the recorded stamp, minimum 15.60 s, 95th percentile 35.49 s,
maximum 96.58 s, and never earlier: 0 of 56,593 resolve before their stamp.
The block therefore carries `tau__reach_read` alongside `tau__reach`, and
`reach_derivable_at_decision` is true on 0 of 85,442 mints. Every `reach_*`
column is outside the admissible feature set. Additionally, `reach__route` is
`guest` on all 346,972 rows carrying a block, meaning the credential-free
fallback served the whole capture at roughly 1% of the primary route's
throughput, so reach coverage is a floor.

**1,225 mints (1.4337%) carry a negative age at first sighting, minimum
-27.6723 s.** A token cannot be observed before it is created, so this is a
stamp error. The known mechanism is that the capture client writes `seen_at`
before it issues the vendor call. It is unresolved and reported as a bound:
read every observer-stamped field as derivable at `seen_at + 27.68 s`, which
costs 28.2% of the 75.0 s cadence, or accept a lookahead of up to 27.68 s and
say so.

**Curve-progress proxies must not be used as features.** `features.parquet`
already excludes them. `observations.parquet` keeps them, under
`gate_inputs__progress`, `gate_inputs__market_cap`, `gate_inputs__liquidity`,
`market_cap_sol`, `vault` and `vault_implied_volume_sol`, because it is the
raw instrument record. A screen on `first_progress >= 0.70` returns a
30.4-fold lift at 100% precision purely by construction. The full 21-name ban
list is in `DATASHEET.md`.

**`launch_windows.jsonl.gz` was repaired.** The source file is a multi-member
gzip whose first member was truncated by an interrupted writer, so a plain
`gzip.open` returns 130 of 999 records without raising. The released copy is
recovered member by member and rewritten as one clean member.

## Field reference: the tau stamps

| Column | Meaning |
| --- | --- |
| `tau__gate_inputs` | derivability time of the vendor screen block, epoch ms |
| `tau__vendor_audit` | derivability time of the vendor audit block, epoch ms |
| `tau__reach` | as-recorded stamp of the X reach block, the poll instant |
| `tau__reach_read` | **corrected** stamp: when the X read actually resolved |
| `tau__fold` | derivability time of the chain fold aggregates |
| `tau__chain_volume_sol` | derivability time of folded chain volume |
| `tau__fees_sol` | derivability time of the fee reading |
| `tau__market_cap_sol` | derivability time of the SOL market capitalisation |
| `tau__vault` | derivability time of the creator vault address |
| `tau__vault_implied_volume_sol` | derivability time of vault-implied volume |

A field is admissible for a decision at time `t` when its stamp is strictly
less than `t`. Observer-recorded fields use the observation instant, never a
vendor-supplied creation timestamp, and the resulting algebra is a bound
rather than an identity.

## Citation

```bibtex
@misc{ouallaf2026trenches,
  title        = {Trenches pump.fun Forward Capture 2026-08: a point-in-time
                  dataset of Solana bonding-curve launches with per-field
                  derivability stamps},
  author       = {Ouallaf, Moussa},
  year         = {2026},
  howpublished = {Hugging Face Hub},
  url          = {https://huggingface.co/datasets/Tr4m0ryp/trenches-pumpfun-forward-2026-08},
  note         = {730,850 observations over 85,442 mints, 2026-08-06 to
                  2026-08-13. X layer dehydrated, raw vendor payload withheld.}
}
```

The measurement programme this dataset was built for:

```bibtex
@misc{ouallaf2026retrenched,
  title  = {reTRENCHed: Measuring Where Memecoin Edge Is Not},
  author = {Ouallaf, Moussa},
  year   = {2026}
}
```

## Licence

PolyForm Noncommercial License 1.0.0. Source-available, noncommercial use with
attribution, no resale. Copyright Keygraph, Inc.

Two carve-outs apply independently. The blockchain-derived files describe
public ledger state that no one owns, so the licence covers this compilation
and its derived columns rather than the underlying public facts. Any content
recovered by rehydrating `post_ids.csv` comes from X under X's terms, not
under this licence.
