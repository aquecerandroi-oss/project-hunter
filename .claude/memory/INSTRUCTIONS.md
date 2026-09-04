# Project memory — rules (tier one)

This folder is the always-loaded memory of PROJECT HUNTER for any Claude Code session or subagent.

## Files
- `MEMORY.md` — the index: one line per saved fact, linking to its topic file. Read it in full at session start.
- `<slug>.md` — one topic file per memory with this frontmatter:

```
---
name: kebab-case-slug
description: one-line summary — used to judge relevance in a future session
metadata:
  type: feedback | architecture | business-rule | reference
---
```

`type` has exactly four values. `feedback` = a mistake a session made that had to be corrected. `architecture` = a pattern found only after failed attempts. `business-rule` = affects the code but is invisible in it. `reference` = where something outside the repo lives.

## What's worth saving — the narrow test
Save only when the answer is yes: **would a future session be surprised and grateful to know this before starting, rather than discovering it the hard way?**

- Derivable by reading the code, `docs/`, or git history → don't save.
- A deadline, a motivation, anything temporary → don't save.
- A debugging recipe that belongs in a commit message → don't save.
- Already in `CLAUDE.md` or `docs/` → don't save (link to it if needed).

Err toward not saving. A small, high-signal index beats a large, ignored one.

## Growth policy — the index stays under 130 non-blank lines
Before adding an entry, count `MEMORY.md`'s non-blank lines. Past 130, sanitize first:
1. Score each entry: recency × specificity × likelihood of preventing a real future mistake.
2. Migrate low-scoring entries to tier two — **never just delete** — in this order: dedup against tier two → match the ADR template → create the note → read it back → only then delete the index line and topic file.
3. Rewrite the index with what's left, then add the new entry.

## Tier two — long-term store
`docs/decisions/` (Architecture Decision Records, Portuguese, template in `docs/decisions/README.md`). Accessed by direct file edit; one ADR per decision, numbered, never rewritten — superseded ADRs get a "Substituído por" line.
