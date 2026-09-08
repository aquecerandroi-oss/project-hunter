# Brief T3.46 — o Radar prevê alguma coisa? Anomalias e score de oportunidade cruzados com os resultados do Lab (Everton, 2026-09-08 19:25: "e o radar, o que ele tá fazendo, não tá ajudando?")

**Owner:** quant-engineer (research, read-only). **Second opinion:** Astra on the study design if a real doubt appears. **Do not commit.** **Operational rule: never a background shell; foreground commands with a timeout <= 5 min; the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a` (git-guard blocks); do not touch `.env*`; VPS read-only (SQL, `repeatable read read only`).** Base: `main` at `c9691d0`. Write scope: `infra/scripts/sql/research/2026-09-09-radar-*.sql`, `.claude/state/exp-drafts/KB-0078-o-radar-preve.md`, `.claude/state/notes-T3.46.md`.

## What the Radar is (read first)
`services/scanner-worker/**` (baselines, anomaly detection, opportunity scoring — `docs/PIPELINE.md` §3–4), the tables it writes (`anomalies`, `opportunities`/`opportunity_scores`, `market_baselines` — check `docs/DATABASE.md`), `apps/api/hunter_api/routers/radar*.py` (what the page shows), and how strategies read the tape (`hunter_core/strategies/base.py` `StrategyContext`: candles, funding, OI, eligibility — **no** Radar field). Fact to state plainly in the KB: today no strategy consumes the Radar.

## Deliver (all numbers from SQL you paste; `as_of`/`read_at`)
1. **Inventory**: how many anomaly events and opportunity scores exist per day and per type over the last 31 days; coverage by market; how the score is distributed (deciles).
2. **Predictive value, simplest honest test**: for every closed Lab outcome (all cohorts, prospective and replay, per version) join the Radar state of the same market at decision time (latest anomaly within N bars = 4/16/96; opportunity score bucket at the decision bar or the last one before it). Table: expectancy gross/net, hit rate, PF, n — **with Radar signal vs without**, per version and pooled; the difference with a day-block bootstrap CI (reuse `.claude/state/exp-drafts/t342-blocos/blocos.py`). Same for score deciles (monotonic?).
3. **Forward returns without strategies** (independent of the Lab's entries): for each anomaly event, the market's return over the next 1 h / 4 h / 24 h vs the matched baseline (same market, random bars without anomaly, same count) — does the anomaly carry information at all?
4. **Verdict in plain Portuguese** (≤ 10 lines): does the Radar predict? which type/score? what N? Then the recommendation: (a) a Radar-gated variant of which strategy (by parameter if a parameter exists; otherwise the brief for a `radar_gate` field in `StrategyContext` — which moves the digest of the live versions: say it), or (b) demote the Radar to a monitoring panel and stop investing.
5. KB-0078 draft (template shape, SQL provenance) for Sexta-feira.

## Prove
SQL with output; report in Portuguese, extended format; `.claude/state/notes-T3.46.md`.
