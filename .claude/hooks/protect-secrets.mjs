#!/usr/bin/env node
// PreToolUse (Edit|Write) — refuses writes to secret-bearing files and writes
// that contain something that looks like a real credential.
//
// This is a security hook, so it is deliberately fail-CLOSED on a positive
// match and fail-OPEN on "nothing usable to evaluate" (bad stdin, missing
// fields). Uses parseHookEvent — the JSON.parse("null") case is handled.
//
// Exit codes: 0 = allow, 2 = block (stderr is shown to the agent as the reason).
import path from "node:path";

import { parseHookEvent, readStdinRaw } from "./hook-io.mjs";

const event = parseHookEvent(readStdinRaw());
if (event === null) {
  process.exit(0);
}

const filePath = String(event?.tool_input?.file_path ?? "").replace(/\\/g, "/");
const base = path.posix.basename(filePath);

// 1. Files that must never be written by an agent. `.env.example` and
//    `*.example` variants are documentation and stay allowed.
const isEnvFile = /^\.env(\..+)?$/.test(base) && !/\.example$/.test(base);
const isKeyMaterial = /\.(pem|key|p12|pfx|jks)$/i.test(base);
if (isEnvFile || isKeyMaterial) {
  console.error(
    `Blocked: "${filePath}" is a secrets file. Agents never write .env or key material — ` +
      `edit .env.example instead and ask the user to fill real values locally.`,
  );
  process.exit(2);
}

// 2. Content scan. Covers Write (content), Edit (new_string) and multi-edit shapes.
const input = event?.tool_input ?? {};
const chunks = [];
if (typeof input.content === "string") chunks.push(input.content);
if (typeof input.new_string === "string") chunks.push(input.new_string);
if (Array.isArray(input.edits)) {
  for (const edit of input.edits) {
    if (typeof edit?.new_string === "string") chunks.push(edit.new_string);
  }
}
const text = chunks.join("\n");
if (!text) {
  process.exit(0);
}

const patterns = [
  [/sk-ant-[A-Za-z0-9_-]{20,}/, "Anthropic API key"],
  [/AKIA[0-9A-Z]{16}/, "AWS access key id"],
  [/-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----/, "private key block"],
  [/gh[pousr]_[A-Za-z0-9]{36,}/, "GitHub token"],
  [/sk_(?:live|test)_[0-9A-Za-z]{24,}/, "Stripe secret key"],
  [/xox[baprs]-[0-9A-Za-z-]{10,}/, "Slack token"],
  [/postgres(?:ql)?(?:\+asyncpg)?:\/\/[^:\s/]+:[^@\s]{8,}@(?!localhost|127\.0\.0\.1|postgres\b)/, "database URL with embedded password"],
  [/redis(?:s)?:\/\/[^:\s/]*:[^@\s]{8,}@(?!localhost|127\.0\.0\.1|redis\b)/, "redis URL with embedded password"],
  [/\b(?:BINANCE|BYBIT|OKX|KRAKEN|COINBASE)_API_(?:KEY|SECRET)\s*=\s*['"]?[A-Za-z0-9]{24,}/, "exchange API credential"],
  [/\bCLERK_SECRET_KEY\s*=\s*['"]?sk_(?:live|test)_[A-Za-z0-9]{10,}/, "Clerk secret key"],
];

for (const [regex, label] of patterns) {
  if (regex.test(text)) {
    console.error(
      `Blocked: the text being written to "${filePath}" contains what looks like a ${label}. ` +
        `Secrets go in the provider's environment, never in the repository. ` +
        `If this is a deliberate fake for a test, make it obviously fake (e.g. "sk-ant-FAKE-for-tests").`,
    );
    process.exit(2);
  }
}

process.exit(0);
