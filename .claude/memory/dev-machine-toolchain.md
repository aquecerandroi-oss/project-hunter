---
name: dev-machine-toolchain
description: the Windows dev machine had no node, npm, pnpm, uv or docker on 2026-09-04; only a Windows Store python stub was on PATH
metadata:
  type: reference
---

Windows 11 dev machine. Node 24 + npm were installed on 2026-09-04 at `C:\Program Files\nodejs` (in the machine PATH, but shells opened before the install do not see it — prepend `/c/Program Files/nodejs` to PATH in Bash or restart the app). Still absent as of that date: `pnpm`, `uv`, `docker`, `gh`; `python` resolves to the Microsoft Store alias. Hooks in `.claude/hooks/` and `packages/config/eslint/verify.mjs` were executed successfully once Node was available. Re-check with `node --version && pnpm --version && uv --version && docker --version` before dispatching any wave that runs commands; delete this note once everything is installed.
