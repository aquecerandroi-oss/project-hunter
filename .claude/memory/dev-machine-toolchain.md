---
name: dev-machine-toolchain
description: the Windows dev machine had no node, npm, pnpm, uv or docker on 2026-09-04; only a Windows Store python stub was on PATH
metadata:
  type: reference
---

Windows 11 dev machine, toolchain installed on 2026-09-04. Shells opened before an install do not see new PATH entries: in the Bash tool prepend `/c/Program Files/nodejs:/c/Users/evert/AppData/Roaming/npm:/c/Users/evert/AppData/Local/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe:/c/Users/evert/.local/bin` to PATH, or ask the user to restart the app. Locations: Node 24 `C:\Program Files\nodejs`; pnpm 11 `%APPDATA%\npm` (installed with `npm -g`, not corepack); uv 0.12 in the WinGet Packages dir above; Python 3.12.14 managed by uv (`uv run` always works; bare `python` may still hit the Microsoft Store alias). Docker Desktop and `gh` still absent — Docker needs admin, WSL2 and license acceptance, so it is the user's call. Hooks and `verify.mjs` were executed successfully with Node.
