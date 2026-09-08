#!/usr/bin/env node
// PreToolUse (Bash) — the working tree is shared by many agents at once, so a
// handful of git commands are never allowed from a tool call: they rewrite or
// discard other agents' uncommitted work (three incidents on 2026-09-07/08:
// `git stash` from a subagent, and two directory-wide `git add` sweeps).
//
// House rule (.claude/rules/parallel-subagent-driven-development.md): commit by
// exact pathspec only — `git add <files> && git commit -- <files>`.
//
// Fail-CLOSED on a match, fail-OPEN when there is nothing to evaluate.
// Exit codes: 0 = allow, 2 = block (stderr is shown to the agent as the reason).
import { statSync } from "node:fs";

import { parseHookEvent, readStdinRaw } from "./hook-io.mjs";

const event = parseHookEvent(readStdinRaw());
if (event === null || event?.tool_name !== "Bash") {
  process.exit(0);
}
const command = String(event?.tool_input?.command ?? "");
if (!/\bgit\b/.test(command)) {
  process.exit(0);
}

const RULES = [
  [/\bgit\s+stash\b/, "git stash mexe no trabalho não commitado de todos os agentes"],
  [/\bgit\s+checkout\s+(--|\.)(\s|$)/, "git checkout -- / . descarta edições de outros agentes"],
  [/\bgit\s+restore\b(?!.*--staged)/, "git restore descarta edições de outros agentes"],
  [/\bgit\s+reset\s+--hard\b/, "git reset --hard descarta a árvore compartilhada"],
  [/\bgit\s+clean\b/, "git clean apaga arquivos não rastreados de outros agentes"],
  [/\bgit\s+commit\b[^|;&]*\s-a(\s|$|m)/, "git commit -a varre arquivos de outros agentes"],
  [/\bgit\s+commit\b[^|;&]*--all\b/, "git commit --all varre arquivos de outros agentes"],
  [/\bgit\s+add\s+(-A|--all|\.|-u|--update)(\s|$)/, "git add -A / . / -u varre arquivos de outros agentes"],
  [/\bgit\s+push\b[^|;&]*(--force|-f)(\s|$)/, "git push --force reescreve o histórico compartilhado"],
];

// `git add <diretório>`: any argument that is an existing directory is a sweep.
// Checked against the real filesystem (relative to the repo root the hook runs
// in), so `git add apps/web` is blocked and `git add apps/web/lib/api/lab.ts` is not.
function addedDirectories(cmd) {
  const found = [];
  for (const segment of cmd.split(/\|\||&&|;|\|/)) {
    const m = /\bgit\s+add\s+(.+)$/.exec(segment.trim());
    if (!m) continue;
    for (const raw of m[1].split(/\s+/)) {
      const arg = raw.replace(/^["']|["']$/g, "");
      if (!arg || arg.startsWith("-") || arg === "--") continue;
      try {
        if (statSync(arg).isDirectory()) found.push(arg);
      } catch {
        // not an existing path: a new file, a glob, or a typo — git decides
      }
    }
  }
  return found;
}
const dirs = addedDirectories(command);
if (dirs.length > 0) {
  console.error(
    `Bloqueado pelo git-guard: git add de diretório (${dirs.join(", ")}) varre arquivos de outros agentes. ` +
      `Liste os arquivos exatos: git add <arquivo1> <arquivo2> && git comm` + `it -- <os mesmos arquivos>.`,
  );
  process.exit(2);
}

for (const [pattern, reason] of RULES) {
  if (pattern.test(command)) {
    console.error(
      `Bloqueado pelo git-guard: ${reason}. ` +
        `Regra da casa: árvore compartilhada — commit só por pathspec exato ` +
        `(git add <arquivos> && git comm` + `it -- <arquivos>); nunca stash/checkout --/restore/reset/clean/commit -a.`,
    );
    process.exit(2);
  }
}
process.exit(0);
