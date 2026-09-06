import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Static safety net for the two architecture rules the brief calls out
 * explicitly (CLAUDE.md; ESLint already enforces both, this pins them for
 * the T2.7 file set specifically): no `console.*`, and `components/**`
 * never imports `@/lib/server/**`.
 */
const ROOT = join(process.cwd(), "components");
const TARGET_DIRS = ["radar", "opportunities", "anomalies", "dashboard"];

function listFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...listFiles(full));
    else if (entry.endsWith(".ts") || entry.endsWith(".tsx")) out.push(full);
  }
  return out;
}

const files = TARGET_DIRS.flatMap((dir) => listFiles(join(ROOT, dir)));

describe("T2.7 components: no console.*, no @/lib/server import", () => {
  it("found the expected component files (guards against an empty/mistyped glob passing vacuously)", () => {
    expect(files.length).toBeGreaterThan(10);
  });

  it.each(files)("%s", (file) => {
    const content = readFileSync(file, "utf-8");
    expect(content).not.toMatch(/console\.(log|warn|error|info|debug)/);
    // Only real import statements count -- several files' own docstrings
    // *name* the forbidden boundary (`@/lib/server`) in prose to explain why
    // they don't cross it, which would otherwise self-trigger this check.
    expect(content).not.toMatch(/from\s+["']@\/lib\/server/);
  });
});
