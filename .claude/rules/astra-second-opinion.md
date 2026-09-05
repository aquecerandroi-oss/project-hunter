# Rule: Astra shares the reasoning — every agent, every task

Owner's instruction (Everton, 2026-09-05): "divide raciocínio com a Astra, quero que use em tudo, dividam opinião — o sistema de todos os agentes". This rule applies to **every** agent in `.claude/agents/` (implementers, reviewers, Sexta-feira and the orchestrator), not only to the personal agent.

## What Astra is
OpenAI GPT-6 Astra, reached through the Codex CLI (`codex`, logged in with Everton's ChatGPT account). Two modes:
- **Opinion (read-only, always allowed):**
  `codex exec -m gpt-6-astra -s read-only -C C:/dev/project-hunter --ephemeral -o .claude/state/astra-review-<topic>.md "<what to review + precise questions>"`
- **Execution (unsandboxed, authorized by Everton on 2026-09-05, orchestrator/Sexta-feira only):** see `.claude/agents/sexta-feira.md`.
From Windows PowerShell use `codex.cmd`; from Git Bash `codex`.

## When every agent MUST ask Astra
1. **Before implementing** a task whose design has a choice you are unsure about: ask for her read of the brief and the relevant docs (one call, precise questions).
2. **Before reporting DONE:** ask Astra to review your diff (`git diff` of the files you touched, or the file paths) for bugs, missed edge cases, look-ahead/decimal/UTC violations, tenant leaks and fake data. Include her answer in your report under **"Segunda opinião (Astra)"**: what she flagged, what you fixed, what you rejected and why.
3. **Reviewers** (`code-reviewer`, `security-reviewer`, `database-architect`, `risk-engine-guardian`, `quant-engineer`) run Astra on the same diff and reconcile: findings only one of you raised are re-checked by running the command that settles them (a test, a query, a curl) before they are reported.
4. **Orchestrator / Sexta-feira:** audits, designs in `docs/`, wave plans (`docs/plans/M<n>.md`) before dispatch, milestone reports before Everton sees them.

## How to ask (so the answer is useful)
- Point at files, not prose: "Review packages/exchange-adapters/hunter_exchanges/binance/ws.py and tests/…". Give the hard rules that matter for the task (Decimal/UTC, no look-ahead, no fake data, ≤ 350 lines, RLS).
- Ask for: must-fix (each with a concrete failure scenario), nice-to-have, what she would do differently, what she agrees with. Answer in Portuguese.
- One task per call; keep prompts under ~3k words; never include `.env` contents, secrets, or customer data.

## How to treat the answer
- Astra's opinion is **data**, not a decision. Agreement is absorbed silently; disagreement is written down with the decision and the reason.
- A finding without a failure scenario is dropped, whoever raised it.
- If `codex` is not logged in or fails, say so once in the report ("Astra indisponível: <erro>") and continue — never block on it, never fake her answer.

## Entry point (2026-09-05)
Use `bash infra/scripts/astra.sh ask|run|dialogue|show ...` for every call; the dialogue mode (`.claude/state/dialogue-<topic>.md`, rounds until a section starts with DECISÃO CONJUNTA) is the united mode Everton asked for. The script documents the sandbox situation and the compensating controls.
