#!/usr/bin/env node
// SessionStart — injects the current milestone, git position and the two
// rules that are cheapest to forget. Pure bonus context, so it is fail-OPEN:
// any problem reading state means "no banner", never "no session".
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

import { parseHookEvent, readStdinRaw } from "./hook-io.mjs";

const event = parseHookEvent(readStdinRaw());
if (event === null) {
  process.exit(0);
}

let milestone = null;
try {
  milestone = JSON.parse(readFileSync(".claude/state/milestone.json", "utf8"));
} catch {
  milestone = null;
}

let head = "unknown";
try {
  head = execFileSync("git", ["log", "-1", "--format=%h %s"], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "ignore"],
  }).trim();
} catch {
  head = "unknown";
}

const lines = [
  "PROJECT HUNTER — session context",
  `HEAD: ${head}`,
];
if (milestone && typeof milestone === "object") {
  lines.push(
    `Milestone: ${milestone.current ?? "?"} (${milestone.status ?? "?"}) — plan: ${milestone.plan ?? "docs/ROADMAP.md"}`,
  );
  if (milestone.next_action) lines.push(`Next action: ${milestone.next_action}`);
  if (Array.isArray(milestone.blockers) && milestone.blockers.length > 0) {
    lines.push(`Blockers: ${milestone.blockers.join("; ")}`);
  }
}
lines.push(
  "Rules: orchestrate, don't implement (dispatch specialists per CLAUDE.md); no live trading; no fake data; agents never commit — the orchestrator commits per task.",
);

process.stdout.write(
  JSON.stringify({
    hookSpecificOutput: {
      hookEventName: "SessionStart",
      additionalContext: lines.join("\n"),
    },
  }),
);
process.exit(0);
