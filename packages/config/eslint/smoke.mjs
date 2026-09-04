// Self-test of the HUNTER web ESLint config (eslint.config.mjs), as it will
// actually be consumed from apps/web. This is deliberately separate from
// ./verify.mjs, which only self-tests the quality/* rule implementations in
// isolation (RuleTester, no config wiring, no import resolution). Here we
// exercise the assembled config against files laid out the way the Next.js
// app is structured, to prove the pieces fit together: file-glob matching,
// per-tier overrides (lib/logger.ts), and the architecture-boundary rule.
//
// Usage: node eslint/smoke.mjs
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { ESLint } from "eslint";

const here = path.dirname(fileURLToPath(import.meta.url));
const CONFIG_FILE = path.join(here, "eslint.config.mjs");

// A throwaway directory that mimics the apps/web layout (app/, components/,
// lib/, hooks/) so the config's `files` globs -- which are matched relative
// to `cwd` -- resolve the same way they will inside the real app.
const root = fs.mkdtempSync(path.join(os.tmpdir(), "hunter-eslint-smoke-"));

function makeEslint() {
  return new ESLint({
    cwd: root,
    overrideConfigFile: CONFIG_FILE,
    // The alias "@/lib/server/api" has no real tsconfig/paths mapping in
    // this throwaway directory, so import-x/no-unresolved would flag every
    // aliased import here regardless of the rule under test. Disabling it
    // only for this smoke run (never in the shipped config) keeps the
    // assertions focused on the quality/* rules they name.
    overrideConfig: { rules: { "import-x/no-unresolved": "off" } },
  });
}

function countErrors(messages, ruleId) {
  return messages.filter((m) => m.ruleId === ruleId && m.severity === 2).length;
}

async function lint(relativePath, code) {
  const eslint = makeEslint();
  const filePath = path.join(root, relativePath);
  const [result] = await eslint.lintText(code, { filePath });
  return result;
}

// (a) a clean file in lib/ yields zero errors.
{
  const result = await lint(
    "lib/format.ts",
    "export function formatUsd(cents: number): string {\n  return `$${(cents / 100).toFixed(2)}`;\n}\n"
  );
  assert.equal(result.errorCount, 0, `expected 0 errors, got ${JSON.stringify(result.messages)}`);
  console.log("ok - clean lib/format.ts yields 0 errors");
}

// (b) a direct console call in a component is exactly one
// quality/no-direct-console error.
{
  const result = await lint(
    "components/Table.tsx",
    "export function Table() {\n  console.log(\"x\");\n  return null;\n}\n"
  );
  assert.equal(
    countErrors(result.messages, "quality/no-direct-console"),
    1,
    `expected 1 quality/no-direct-console error, got ${JSON.stringify(result.messages)}`
  );
  console.log("ok - components/Table.tsx console.log yields 1 quality/no-direct-console error");
}

// (c) a 360-line file in lib/ trips the whole-file quality/max-lines budget
// (350). Exported bindings so @typescript-eslint/no-unused-vars stays quiet
// and doesn't muddy the assertion.
{
  const lines = Array.from({ length: 360 }, (_, i) => `export const value${i} = ${i};`).join("\n") + "\n";
  const result = await lint("lib/big.ts", lines);
  assert.equal(
    countErrors(result.messages, "quality/max-lines"),
    1,
    `expected 1 quality/max-lines error, got ${JSON.stringify(result.messages)}`
  );
  console.log("ok - 360-line lib/big.ts yields 1 quality/max-lines error");
}

// (d) a component reaching into lib/server (server-only) is a
// quality/no-direct-data-access violation. import-x/no-unresolved is
// disabled above; import-x/no-restricted-paths may or may not also fire
// depending on alias resolution -- irrelevant here, we assert on the
// quality rule's id, not on the total error count.
{
  const result = await lint(
    "components/Nav.tsx",
    "import { apiFetch } from \"@/lib/server/api\";\n\nexport function Nav() {\n  return apiFetch(\"/ping\");\n}\n"
  );
  assert.ok(
    countErrors(result.messages, "quality/no-direct-data-access") >= 1,
    `expected a quality/no-direct-data-access error, got ${JSON.stringify(result.messages)}`
  );
  console.log("ok - components/Nav.tsx importing @/lib/server/api yields quality/no-direct-data-access");
}

// (e) lib/logger.ts is the log adapter itself; the override that turns
// quality/no-direct-console back off for it must apply.
{
  const result = await lint(
    "lib/logger.ts",
    "export function logError(message: string): void {\n  console.error(message);\n}\n"
  );
  assert.equal(
    countErrors(result.messages, "quality/no-direct-console"),
    0,
    `expected 0 quality/no-direct-console errors, got ${JSON.stringify(result.messages)}`
  );
  console.log("ok - lib/logger.ts console.error yields 0 quality/no-direct-console errors");
}

fs.rmSync(root, { recursive: true, force: true });
