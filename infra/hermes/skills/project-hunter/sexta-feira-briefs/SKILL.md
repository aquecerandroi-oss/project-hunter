---
name: sexta-feira-briefs
description: How Sexta-feira turns a request into a brief, delegates it (delegate_task with a role card, Astra via astra.sh, optionally Claude Code), reviews the result adversarially and commits per task on PROJECT HUNTER. Use for any implementation, review or documentation work.
---
# Briefs, delegação, revisão, commit

## When to Use
Every piece of work that is not a one-line answer: implementation, migration, review, docs, tests.

## Procedure
1. **Classify** (CLAUDE.md §6): spike / bounded / architectural. Architectural work gets a design in `docs/` and Everton's approval before code.
2. **Write the brief** at `.claude/state/brief-<task>.md`, in English, self-contained: goal, "Leia antes" (files), exact deliverables numbered, the files it MAY touch and the paths it must NOT touch (always: `.env*`, and whatever other tasks are editing), the verification commands to run and paste (one testcontainers file per `pytest`, foreground, <= 5 min each, never background), the report format (STATUS · FILES · TESTS with real output · CONCERNS), "do not commit". Reuse the shape of the existing briefs in `.claude/state/brief-*.md`.
3. **Pick the executor.**
   - `delegate_task(goal=..., context=...)`: paste the full text of the role card `.claude/agents/<role>.md` (database-architect, risk-engine-guardian, security-reviewer, quant-engineer, backend-specialist, frontend-specialist, exchange-integration-specialist, test-engineer, documentation-writer, code-reviewer, devops-engineer) plus the brief path, the PATH line, the shell rules and the report format. Subagents know nothing you do not paste.
   - Astra (GPT-6, Codex CLI): `bash infra/scripts/astra.sh run <task>` for mechanical, fully specified work; `astra.sh ask` for opinions; `astra.sh dialogue` for contested decisions. Check `git status`/`git diff --stat` after; revert anything outside the brief.
   - Claude Code (`claude -p`), only if logged in and not rate-limited.
   - Parallel only with disjoint file sets; max 3 subagents and max 4 testcontainers suites at once.
4. **Review** every delivery: run its gates yourself when cheap (ruff, pyright, one test file), then `code-reviewer` always, plus `security-reviewer` / `database-architect` / `risk-engine-guardian` / `exchange-integration-specialist` by path, and Astra on every diff. A finding without a concrete failure scenario is dropped; CRITICAL/HIGH are fixed before commit. Write `.claude/state/review-<task>.md`.
5. **Commit per task**: `git add <exact files>` (never `-A`), conventional message in English with the why, trailer `Co-Authored-By: Sexta-feira <sexta-feira@project-hunter.local>`, `git push origin main`. Then Obsidian: changelog entry, bugs, module status.
6. **Deploy** only through `ssh hunter-vps 'cd /opt/project-hunter && MARKET_SHARDS=4 bash infra/vps/compose.sh update'`, only after the reviews, and never when it would apply a migration to Everton's wallet database without telling him first; verify after (alembic head, heartbeats, `/ready`, site 200).

## When you are the executor, not the orchestrator
Sometimes the orchestrator hands **you** a brief (the file already exists in `.claude/state/`). Then the brief binds you exactly as it binds any subagent: touch only the files it lists, run only the commands it lists, write the notes file it names, and **do not commit or push when it says so** — return the diff and the report; the orchestrator reviews and commits. Do not write a second brief for the same task; the existing file is the contract. Before writing STATUS, run `git log -1` and `git status -sb` and report what actually happened (a report saying "not committed" next to a commit on `main` is a broken report). If you delegated part of the work and the subagent crashed, say so in the notes and validate its diff yourself before reporting.

## Pitfalls
- Two implementers on the same glob; enums and models have one owner.
- Committing files of a task still in flight; committing `openapi.json`, `.env*`, `.claude/state/tmp/**`.
- Trusting a report without pasted output. Trusting a green suite that mocks the path it claims to prove.
- Letting a subagent touch `infra/migrations/**` without `database-architect` review, or anything under `packages/risk-core`, `hunter_core.execution`, `services/execution-worker` without `risk-engine-guardian`.

## Verification
A task is closed when: the brief has a notes file, the review file exists, the gates it lists were run with pasted output, the commit is pushed, and the changelog has the line.
