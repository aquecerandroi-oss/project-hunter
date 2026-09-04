---
name: dev-machine-toolchain
description: the Windows dev machine had no node, npm, pnpm, uv or docker on 2026-09-04; only a Windows Store python stub was on PATH
metadata:
  type: reference
---

On 2026-09-04 the developer's Windows 11 machine had none of the M0 prerequisites on PATH (Git Bash and PowerShell both): no `node`, `npm`, `pnpm`, `uv`, `docker`, `gh`, `claude` CLI. `python` resolved to the Microsoft Store alias. Consequences: the Node-based hooks in `.claude/hooks/` and `packages/config/eslint/verify.mjs` could not be executed to prove they work; `docs/plans/M0.md` lists the install steps. Re-check with `node --version && pnpm --version && uv --version && docker --version` before dispatching any wave that runs commands, and update or delete this note once the toolchain is installed.
