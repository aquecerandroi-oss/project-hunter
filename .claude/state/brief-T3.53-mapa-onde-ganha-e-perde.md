# Brief T3.53 — o mapa de onde cada versão ganha e perde: 6 854 desfechos cruzados por mercado, hora do dia (Brasília e UTC), dia da semana, regime horário do BTC, faixa de custo e coorte — com controle de multiplicidade, para separar padrão de acaso (Everton, 2026-09-08 23:20)

**Owner:** quant-engineer (research, read-only). **Do not commit.** **Operational rule: never a background shell; foreground commands with a timeout <= 5 min; no testcontainers; the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a` (git-guard blocks); do not touch `.env*`; VPS strictly read-only (`repeatable read read only`).** Base: `main` at HEAD. Write scope: `infra/scripts/sql/research/2026-09-09-t353-*.sql`, `.claude/state/exp-drafts/t353/` (CSV + scripts), `.claude/state/exp-drafts/KB-0079-onde-ganha-e-perde.md`, `.claude/state/notes-T3.53.md`.

## Deliver
1. **Population**: every terminal outcome with `r_multiple`, joined to version, cohort (replay/prospective), market, `source_bar_close`, the hourly BTC regime row with `end_time <= source_bar_close` (the previous closed hour — never the hour in progress), toll bucket (`custo_R` from KB-0076 identity: < 0,10 / 0,10–0,20 / > 0,20), hour of day (BRT and UTC), weekday. Paste counts per version and per cell size.
2. **Cells**: for each version with n ≥ 100 (and pooled by strategy family), expectancy net, PF, hit rate, n per cell of each dimension; day-block bootstrap CI (reuse `t342-blocos/blocos.py`) for the difference cell − rest; **multiplicity**: Holm over all cells tested per version, and a minimum cell size (n ≥ 30, ≥ 7 distinct days) — cells below are shown but marked "não julgável".
3. **The two rankings Everton asked for**: where each version wins (top cells that survive Holm) and where it loses (bottom cells) — and the honest count of how many cells were tested vs how many survived.
4. **Regime specifically** (feeds T3.52): expectancy per regime label per family, with the share of decisions in `UNKNOWN`.
5. **Verdict in ≤ 10 lines of Portuguese**: is there any filter (market/hour/weekday/regime/toll) that survives multiplicity for any version; which one to turn into a variant first; what is noise.
6. KB-0079 draft (template shape, SQL provenance, timestamps in Brasília).

## Prove
SQL with output, bootstrap outputs, report in Portuguese, extended format; `.claude/state/notes-T3.53.md`.
