#!/usr/bin/env node
// PreToolUse (Read|Grep|Glob|Write|Edit) — the Obsidian vault is MCP-only.
// Direct file access skips the vault's frontmatter/template/link validation,
// so any tool call whose path touches `vault/` is refused, except read-only
// access to the rotating `vault/daily/` notes. Fail-open on unusable input.
// Pattern from vibe-coding-toolkit docs/tools/08-obsidian-memory.md.
import { parseHookEvent, readStdinRaw } from "./hook-io.mjs";

const event = parseHookEvent(readStdinRaw());
if (event === null) {
  process.exit(0);
}

const input = event?.tool_input ?? {};
const raw = String(input.file_path ?? input.path ?? input.pattern ?? "").replace(/\\/g, "/");
if (!raw) {
  process.exit(0);
}

// Only the project's own vault; unrelated paths that merely contain "vault"
// (e.g. a dependency named *vault*) are not the target.
const isVault = /(^|\/)vault\/(?!README\.md$)/.test(raw) && !/node_modules\//.test(raw);
if (!isVault) {
  process.exit(0);
}

const tool = String(event?.tool_name ?? "");
const isDailyRead = /(^|\/)vault\/daily\//.test(raw) && ["Read", "Grep", "Glob"].includes(tool);
const isTemplateRead = /(^|\/)vault\/templates\//.test(raw) && ["Read", "Grep", "Glob"].includes(tool);
if (isDailyRead || isTemplateRead) {
  process.exit(0);
}

console.error(
  `vault/ is MCP-only: use the vault MCP tools (search, read note, create/update note) instead of ${tool || "direct file access"} on "${raw}". ` +
    "Direct edits bypass frontmatter, template and wikilink validation.",
);
process.exit(2);
