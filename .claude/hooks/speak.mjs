#!/usr/bin/env node
// PROJECT HUNTER — Stop hook: gives Sexta-feira a voice.
// Reads the hook event from stdin (Claude Code passes {transcript_path, ...}),
// takes the last assistant message of the transcript, strips markdown/code,
// keeps it short, and speaks it with the Windows pt-BR voice (Microsoft Maria)
// through System.Speech (SAPI). Fail-open: any problem → exit 0 silently.
//
// Off switch: set HUNTER_VOICE=0 in the environment, or create the file
// .claude/state/voice-off (delete it to turn the voice back on).

import { existsSync, readFileSync } from "node:fs";
import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const MAX_CHARS = 700;
const VOICE = process.env.HUNTER_VOICE_NAME || "Microsoft Maria Desktop";

function readStdin() {
  try {
    return readFileSync(0, "utf8");
  } catch {
    return "";
  }
}

function lastAssistantText(transcriptPath) {
  const lines = readFileSync(transcriptPath, "utf8").split(/\r?\n/).filter(Boolean);
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    let entry;
    try {
      entry = JSON.parse(lines[i]);
    } catch {
      continue;
    }
    const message = entry?.message ?? entry;
    if ((entry?.type ?? message?.role) !== "assistant" && message?.role !== "assistant") continue;
    const content = message?.content;
    const parts = Array.isArray(content)
      ? content.filter((c) => c?.type === "text").map((c) => c.text)
      : typeof content === "string"
        ? [content]
        : [];
    const text = parts.join("\n").trim();
    if (text) return text;
  }
  return "";
}

function speakable(text) {
  let t = text;
  t = t.replace(/```[\s\S]*?```/g, " código omitido. ");
  t = t.replace(/`([^`]*)`/g, "$1");
  t = t.replace(/^\s*\|.*\|\s*$/gm, " "); // tables
  t = t.replace(/^[-*]\s+/gm, "");
  t = t.replace(/[#>*_]+/g, "");
  t = t.replace(/\[([^\]]+)\]\([^)]*\)/g, "$1");
  t = t.replace(/https?:\/\/\S+/g, " link ");
  t = t.replace(/\s+/g, " ").trim();
  if (t.length > MAX_CHARS) t = `${t.slice(0, MAX_CHARS)}… o resto está na tela.`;
  return t;
}

function main() {
  if (process.platform !== "win32" || process.env.HUNTER_VOICE === "0") return;
  const here = dirname(fileURLToPath(import.meta.url));
  if (existsSync(join(here, "..", "state", "voice-off"))) return;
  let event = {};
  try {
    event = JSON.parse(readStdin() || "{}");
  } catch {
    return;
  }
  const transcript = event.transcript_path;
  if (!transcript || !existsSync(transcript)) return;
  const text = speakable(lastAssistantText(transcript));
  if (!text) return;
  const escaped = text.replace(/'/g, "''");
  const script =
    "Add-Type -AssemblyName System.Speech; " +
    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; " +
    `try { $s.SelectVoice('${VOICE}') } catch {} ; ` +
    "$s.Rate = 1; " +
    `$s.Speak('${escaped}')`;
  const child = spawn("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", script], {
    detached: true,
    stdio: "ignore",
    windowsHide: true,
  });
  child.unref();
}

main();
