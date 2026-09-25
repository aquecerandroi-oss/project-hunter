# Rule: Obsidian first — every strategy change

Owner's instruction (Everton, T4.93): "sempre que for usar a estratégia tem
que passar analisando via Obsidian primeiro" — every use of a strategy is
analysed via Obsidian first.

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
