# Brief T3.38c — fecha a revisão REQUEST_CHANGES da T3.38: a identidade da operação inclui o stop, normaliza Decimal, usa separador seguro no SQL; a tela não esconde R divergente entre irmãs

**Owners:** T3.38c-api backend-specialist; T3.38c-web frontend-specialist. **Reviewer afterwards:** code-reviewer (same reviewer). **Do not commit.** **Operational rule: never a background shell; foreground commands with a timeout <= 5 min; testcontainers one file per pytest invocation; the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a` (git-guard blocks); add exact files only; do not touch `.env*`; do not stop or recreate local stack containers.** Base: `main` at `62e638b`.

## Review findings (code-reviewer on 96eea21/cb18c1a/c86ed19)
- Finding 1 (SHADOW-LAB §Funil "written by T3.38b") is a misattribution: the section is T3.36's text, swept into 96eea21 by a concurrent commit (T3.36's own report says so). **No revert.** T3.38c-web only fixes the false line in `.claude/state/notes-T3.38.md:23` ("não tocado §Funil" → "a seção §Funil é da T3.36 e foi arrastada por este commit").
- Finding 2 (HIGH): `identity_key` ignores `stop`; sibling versions with different `stop_atr` can share entry/exit/result but differ in R and money; the card sums only the first member. Fix (API): add `stop` (virtual stop price) to the tuple. Fix (web): if members of a group still differ in `r_multiple`/money (should now be impossible), do not merge money silently: show the range ("+34,00 a +41,20 USDT") and a note; test with divergent R.
- Finding 3 (MEDIUM): normalize Decimals in `compute_identity_key` (`Decimal.normalize()` or `quantize(Decimal("1e-10"))`, same on the SQL side via `::numeric(28,10)` cast) — test "1.16930116" vs "1.169301160" collide.
- Finding 4 (MEDIUM): SQL `_IDENTITY_KEY_TEXT` uses `"|"`; Python uses `\x1f`. Use `chr(31)` in SQL too (`E'\x1f'`) and assert Python == SQL key for a seeded row (integration test).
- Finding 5 (MEDIUM): "desta página" (client, merges only across versions) vs "de todas as concluídas" (server, pure DISTINCT) can diverge if a same-version duplicate exists. Web: dedupe the page by `identity_key` alone for the card's money (same rule as the server) while keeping the row-merge rule for display; test.
- Finding 6 (LOW): log a `console.warn` once when `distinct_operations` is missing.

## Prove
API: unit + integration per file, `ruff`/`pyright`; `pnpm gen:types` if the schema changes (it does not — only the hash input). Web: `pnpm --filter web lint|typecheck|test`. Reports in Portuguese, extended format; append "T3.38c-api"/"T3.38c-web" to `.claude/state/notes-T3.38.md`.
