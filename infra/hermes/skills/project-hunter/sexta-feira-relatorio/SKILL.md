---
name: sexta-feira-relatorio
description: The report formats Sexta-feira uses on PROJECT HUNTER — the compact status table for Everton, the extended task report, the milestone close (§77) and the approval/rejection wording. Use before answering "como estamos", closing a task, or judging a milestone.
---
# Relatórios da Sexta-feira

## When to Use
Any status answer to Everton, any task closure, any milestone report or approval decision.

## Procedure
### 1. "Como estamos" — compact table (Portuguese)
| Feito | Rodando | Bloqueado | Precisa de você |
One or two lines per cell, commit hashes for what landed, agent/task names for what runs, the concrete blocker and its owner, and exactly what Everton must do with his own hands (a command in a `bash` block, a decision phrased as one question). Close with one short, speakable paragraph.

### 2. Task report (extended format, Portuguese, real output)
STATUS (DONE / DONE_WITH_CONCERNS / BLOCKED) · FILES (created / modified, absolute paths) · TESTS (each command and its pasted real output; testcontainers files one per invocation) · REAL DATA / PROOF (what was observed live, with timestamps) · CONCERNS (each with a concrete failure scenario) · what was NOT done and why. A "done" without command output is not done.

### 3. Milestone close — §77 (docs/reports/M<n>.md)
COMPLETED · FILES CREATED · FILES MODIFIED · DATABASE CHANGES · TESTS CREATED · TEST RESULTS (real output) · REAL DATA CONNECTED · MOCKS REMAINING · BUGS · SECURITY ISSUES · OBSIDIAN UPDATED · KNOWN ISSUES · NEXT MILESTONE. Every objective of the milestone's "definition of done" gets its evidence line.

### 4. Approval on Everton's behalf (delegated 2026-09-05)
Criteria are objective: every objective met with real output; lint, typecheck, tests and container build green; every CRITICAL/HIGH finding closed or recorded as a known limitation with a scenario; no fake data or inert control; Obsidian and docs updated; report in the extended format. Approve: write "APROVADO pela Sexta-feira em <data> em nome do Everton" at the top of the report, set `milestone.json` (`status: closed`, `current: M<n+1>`), commit, push, tell Everton in one paragraph what he can now do in the app. Reject: list exactly what blocks, with numbers, and dispatch the fix. Everton can always override.

## Pitfalls
- No em-dash lists of adjectives; no "tudo certo" without the table. Numbers only from commands you ran or reports that pasted output.
- Never claim autonomous mode ready; the directive says only when the complete flow is verified (T3.9) and Everton activated a paper version.

## Verification
Before sending: does every "feito" have a hash or a pasted output? Does every "precisa de você" have one concrete action? Is the last paragraph short enough to be read aloud?
