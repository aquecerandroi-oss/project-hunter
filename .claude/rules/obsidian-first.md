# Rule: Obsidian first — every task, every agent (and every strategy change)

Owner's instructions: "sempre que for usar a estratégia tem que passar
analisando via Obsidian primeiro" (T4.93, 25/09/2026) and, extended to the
whole project on 28/09/2026: "eu quero que o projeto inteiro adquira o
conhecimento e sempre passe pelo Obsidian".

## Every task, not only strategy (28/09/2026)

The Obsidian base (`obsidian/`) is the project's memory graph. **Every**
agent, on **every** task — code, schema, ops, research, UI, docs — does this:

1. **Read before acting.** Start at `obsidian/00-HOME.md`, then the notes of
   the area touched: the module page, the relevant `KB-*` notes (search the
   task's terms in `obsidian/11-KNOWLEDGE/`), open bugs (`07-BUGS/`), the
   decisions that constrain it (`06-DECISIONS/`), and for anything that can
   change what the system buys/sells, `KB-0149`, `Fila de Hipoteses.md`,
   `Mapa de Estrategias.md` and the EXP page. Cite in the brief/report which
   notes you read and what they changed in your plan — "read the docs" is not
   a citation.
2. **Write back what you learned** in the same commit as the task: a lesson
   in the KB/module page, a bug in `07-BUGS`, a decision in `06-DECISIONS`,
   an experiment evaluation (append-only) in `05-EXPERIMENTS`, and the Astra
   synthesis (below). If nothing new was learned, say so in the report.
3. **Link both ways** (`[[...]]`): a note no other note reaches is a neuron
   without synapses. `uv run python infra/scripts/obsidian_lint.py` must stay
   "base limpa" after your change.
4. **Never invent in a note**: numbers come from a command you ran or a note
   you cite; unknowns are written as unknowns.

The orchestrator (Sexta-feira) refuses a report that skips steps 1–2 for a
task where they apply, and the nightly routine (`ficha-diaria-mesa-meme`)
re-checks the lint and the changelog links every day.

## What this means in code

The robots never read Obsidian at decision time — a note is unvalidated
human text, not something a live loop should trust. Instead, the gate runs
the other way round: **no strategy change can reach the robots without an
Obsidian note that covers it.** The audited change tools refuse to apply
without one:

- `infra/scripts/meme_rule_set.py --set-param … --apply` and
  `--deprecate … --apply`
- `infra/scripts/activate_strategy_version.py` (plain activation and
  `--paper-line`, when not `--dry-run`; `--deprecate`/`--supersede` are
  retirements, not "using" the strategy, and are not gated)
- `infra/scripts/spot_desk_markets.py --enable/--disable/--set-mint --apply`

Each requires `--note <path.md under obsidian/>` that exists, is Markdown,
and mentions the exact target (rule-set `name/version`, strategy
`key`/`version`, or market symbol) — case-insensitive text match. A dry run
prints which note would be needed but does not require one. See
`infra/scripts/obsidian_note_gate.py` for the shared check and its named
refusals.

## What every agent does before touching a strategy

Before **proposing, implementing or applying** any strategy change (a rule
set, an activation, a paper line, a spot/1 market toggle):

1. Read `obsidian/11-KNOWLEDGE/KB-0149-o-que-a-mesa-real-ensinou.md`,
   `obsidian/11-KNOWLEDGE/Fila de Hipoteses.md` and the relevant
   `obsidian/05-EXPERIMENTS/EXP-*.md` page for the hypothesis in play.
2. Cite what was read (which notes, what they say) in the task brief and in
   the final report — not just "read the docs", the actual finding that
   shaped the decision.
3. Write the outcome back to Obsidian once the change lands: the verdict
   (`CONFIRMA`/`REFUTA`/`NÃO CONFIRMA` per `docs/RESEARCH.md`), the EXP page's
   evaluation, or a diary entry — whichever the existing structure for that
   note already uses.
4. Pass that note's path to `--note` when calling the audited tool above. A
   change without a note is refused by the tool itself, not just by review.

This rule does not replace `astra-second-opinion.md` or the specialist
routing table — it adds one more precondition specific to strategy changes,
enforced twice: by the agent's own workflow and, structurally, by the tools.

## Astra reviews and dialogues are Obsidian-first too

Every Astra review or dialogue used in a task gets its synthesis note in
`obsidian/06-DECISIONS/Revisoes-Astra/` or `Dialogos/` in the same commit as
the task, linked from the task's notes (KB/EXP/diary). Raw
`.claude/state/astra-review-*.md`/`dialogue-*.md` files are not a substitute
— they are the cited source, not the record.
