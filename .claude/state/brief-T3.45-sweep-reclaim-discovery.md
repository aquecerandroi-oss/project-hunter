# Brief T3.45 — a quarta vaga: contrato da candidata "sweep + reclaim" (varredura de mínima e recuperação), sem código, com pré-checagem por SQL antes de qualquer módulo

**Owner:** quant-engineer (discovery). **Second opinion:** Astra (the orchestrator runs `astra.sh ask` if the contract raises a real doubt). **Do not commit.** **Operational rule: never a background shell; foreground commands with a timeout <= 5 min; the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a` (git-guard blocks); do not touch `.env*`; VPS read-only (SQL only).** Base: `main` at `2df9f67`. Write scope: `.claude/state/exp-drafts/EXP-0017-sweep-reclaim.md`, `.claude/state/brief-T3.45b-sweep_reclaim_v1.md` (the implementation brief), `.claude/state/notes-T3.45.md`, `infra/scripts/sql/research/2026-09-09-sweep-reclaim-precheck.sql`.

## Why
`.claude/state/notes-T3.33.md` shortlist #9 named "sweep + reclaim (spring)" the first substitute after the four; `derivatives` died at its pre-check (T3.33d). Lessons from the day that the contract must absorb: the toll identity (`custo_R = 0,0020 / (stop_atr × ATR%)`, KB-0076 corrected by T3.40) — declare the cap; no invalidation unless argued (KB-0006); the ATR floor 0,006 bites (T3.33d aviso; T3.40 v5 = 0 decisions at 0,020); geometry guards must be checked against real data before freezing (breakout v1: 14/14 rejected); portão C1–C8 filled before code; a pre-check SQL that can kill the candidate (T3.33d method).

## Deliver
1. **Contract** (EXP-0017, template shape): entry = a bar (or 2) whose low sweeps below the prior N-bar swing low (a pivot in the T3.34 sense, k=3) by ≥ `sweep_atr` and **closes back above** it (reclaim), with RVOL ≥ `rvol_min`; stop below the sweep low; target = 2 × risk (or the mid-range) — argue the geometry with the toll identity and the break-even table like T3.33; horizon; no invalidation (the sweep low is the structure); parameters with ranges; kill criteria K1–K5 + "≥ 60 % of decisions from one market".
2. **Pre-check SQL on the VPS (read-only)**: over 31 days × ETH/SOL/XRP/DOGE 15 m bars, count sweep+reclaim events under the frozen rule (at least the rule's geometric part), by market and by ATR% bucket; expected decisions per market-day; share below the ATR floor. Kill rule written before running: < 20 events → do not write the module. Paste the result.
3. **Portão C1–C8** filled in the EXP (honest; declare divergences).
4. **Implementation brief** `brief-T3.45b-sweep_reclaim_v1.md` in the shape of T3.33a–c (module, tests, registry/constraints/seed lines, digests untouched, replay sequence) — only if the pre-check passes; otherwise the EXP is filed `bloqueado-por-precheck` and the brief says so.

## Prove
SQL with output; report in Portuguese, extended format; `.claude/state/notes-T3.45.md`.
