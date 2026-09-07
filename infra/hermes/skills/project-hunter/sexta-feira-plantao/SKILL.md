---
name: sexta-feira-plantao
description: The Sexta-feira standing shift on PROJECT HUNTER — situational read, health of VPS and local stack, integrate finished tasks, dispatch the next one, one dated evaluation per experiment, Obsidian upkeep, one short note for Everton. Run when idle or on the hourly routine.
---
# Sexta-feira de plantão

## When to Use
Every scheduled routine tick, every wake-up without a request, and whenever Everton says "plantão" or "como estamos". Working directory must be `C:\dev\project-hunter`.

## Procedure
1. **Situational read** (read-only): `git status --short`, `git log --oneline -15`, `.claude/state/milestone.json`, the current `docs/plans/M<n>.md`, `.claude/state/plantao.md`, the newest `.claude/state/{review,notes,brief}-*.md`, `obsidian/00-HOME.md`, the latest `obsidian/09-OPERATIONS/Diario/*.md`.
2. **Health.** VPS: `ssh hunter-vps 'cd /opt/project-hunter && git rev-parse --short HEAD && docker ps --format "{{.Names}}\t{{.Status}}" | sort && docker exec hunter-redis-1 redis-cli --raw keys "hb:*" | sort && docker exec hunter-redis-1 redis-cli --raw hgetall hb:execution:paper && curl -sk -o /dev/null -w "site %{http_code}\n" https://127.0.0.1/'`. Local: `docker ps` (Docker Desktop may be off — say so, do not start it). Anything red becomes an entry in `obsidian/07-BUGS/Open Bugs.md` and, when the fix is known and cheap, a brief.
3. **In flight.** Uncommitted files in `git status` belong to a task; find its brief and notes. If the task reported done and nobody integrated it: run the gates it lists (one testcontainers file per `pytest`, foreground), dispatch `code-reviewer` (role card `.claude/agents/code-reviewer.md`) via `delegate_task` with the brief and the diff range, fix via the right specialist, then commit per task and push. Never commit files of a task still running.
4. **Next task.** If nothing is in flight, take the next task of the current plan or the oldest `.claude/state/brief-*.md` without notes. Write the brief if missing (scope, allowed files, verification commands, report format), then `delegate_task` with the full role card content in `context`. Never two implementers on the same file set. Skip anything on the "only Everton decides" list.
5. **Shadow Lab shift.** For every active `obsidian/05-EXPERIMENTS/EXP-*.md`: append ONE `### Avaliação de <AAAA-MM-DD> — as_of = <UTC>` section with numbers pasted from SQL you actually ran (VPS: `docker exec hunter-postgres-1 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f -'`). Never rewrite a previous evaluation; Hypothesis and Protocol are frozen; below 100 evaluable outcomes AND 30 distinct days the result is `inconclusivo`; never activate, deprecate or reparameterise anything.
6. **Base upkeep.** `obsidian/08-CHANGELOG/Changelog.md` (one entry per commit since the last shift), `07-BUGS/Open Bugs.md`, module `status:` lines, `00-HOME.md`, and the day's diary in `09-OPERATIONS/Diario/YYYY-MM-DD.md` (append, never rewrite). Links `[[...]]` in both directions. Commit `obsidian/**` on its own: `docs(obsidian): plantão <data> ...`.
7. **Note for Everton.** Rewrite `.claude/state/plantao.md`: what changed since the last shift, what runs, what is blocked, what needs him (one paragraph each). Reply to him in the compact table: feito / rodando / bloqueado / precisa de você.

## Pitfalls
- Never touch `.env*`; never `docker compose` by hand on the VPS; never start more than 4 testcontainers suites; never a background shell.
- A number you did not measure does not exist. Silence from the Lab is a finding (open a bug), not an excuse to skip the evaluation.
- Do not spend on anything paid; do not enable any `ENABLE_*`; do not activate strategy versions.

## Verification
The shift is done when: `git status` is clean or every dirty file is named in the note as an in-flight task; the diary of the day has today's section; `plantao.md` has today's timestamp; every commit you made is pushed.
