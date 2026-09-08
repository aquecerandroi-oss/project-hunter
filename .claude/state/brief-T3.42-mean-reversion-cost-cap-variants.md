# Brief T3.42 — a única candidata viva ganha as irmãs que o estresse pediu: mean_reversion v1 com teto de pedágio (atr_pct_min 0,008 e 0,010), derivadas, ativadas como pesquisa, replayadas e estressadas

**Owner:** quant-engineer. **Reviewers afterwards:** code-reviewer (receipts). **Do not commit.** **Operational rule: never a background shell; foreground commands with a timeout <= 5 min (slice replays ≤ 4 min with one explicit `--cohort` per variant); the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a` (git-guard blocks); do not touch `.env*`; do not stop or recreate containers; VPS writes only through `derive_variant.py`/`activate_strategy_version.py` and the replay — authorised by Everton for research_only; never paper/agents/flags; if a dry-run prints an unexpected digest (`…mean_reversion_v1@sha256:a970c9d9…`), STOP.** VPS image `d829546` (api/strategy-worker). Base: `main` at `7b0edeb`.

## Why
`.claude/state/stress-mean-reversion-v1-2026-09-08.md`: base +0,094 R, `custos_x2` −0,12 R (IC do Δ inteiro negativo) → **frágil a custos**; T3.33e: 70 % das decisões abaixo de ATR% 1,0 % são líquidas negativas com bruta positiva; stop/alvo ±25 % dentro do ruído. The cost identity (`custo_R = 0,0020 / (stop_atr × ATR%)`, KB-0076 corrected by T3.40) says the only lever that moves the toll is the ATR floor: `atr_pct_min` 0,006 → 0,008 caps the toll at 0,25 R, 0,010 at 0,20 R.

## Deliver
1. Derive **two** variants from `mean_reversion v1`: `--set atr_pct_min=0.008` and `--set atr_pct_min=0.010` (changelog "T3.42: teto de pedágio 0,25 R / 0,20 R (estresse T3.36)"); dry-run, then activate each (10-min capacity watch between them; `momentum v3` paper first; `outbox_lag_s 0`).
2. Replay both, 31 days, ETH/SOL/XRP/DOGE, two contiguous slices per variant, one cohort each, `--explain-ledger`; receipts verbatim.
3. Evaluation paired with the parent cohort `replay:d0f77894-1e04-454e-a49f-d9a98d894968` (T3.26/T3.40 method): decisions, evaluable, gross/net, cost R, PF, hit rate, days; the four paired groups; the EXP-0006 rule (cut > 70 % of decisions = another strategy); exits by reason (the parent's gain sits in 6 horizon exits — say whether it survives the filter).
4. Stress pass on each cohort (`replay.stress`): verdict (only if n ≥ 30 — say so).
5. EXP drafts `EXP-0014-mean-reversion-teto-025.md`, `EXP-0015-mean-reversion-teto-020.md` (template shape, portão C1–C8, REPLAY evaluation); activation timestamps for `Registro de Tentativas` in the notes.

## Prove
Every command with real output, receipts, SQL and tables; report in Portuguese, extended format; `.claude/state/notes-T3.42.md`.
