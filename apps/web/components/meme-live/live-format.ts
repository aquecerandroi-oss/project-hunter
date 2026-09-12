/**
 * Pure formatting for the real executor's panel (T4.17): no React, no fetch
 * -- `tests/meme-live-labels.test.ts`. Every function reads its input
 * defensively (the heartbeat's `gates`/`policy` are `dict[str, Any]` on the
 * API side -- CLAUDE.md's "unavailable never becomes zero" applies to a
 * missing/malformed field here too, never a fabricated default).
 */
import { formatSol } from "@/components/meme/meme-format";
import { formatBrasiliaShort } from "@/lib/time";

/** "9eoC…HWpvzN" -- same 5+5 shape `proposal-card.tsx` uses for a mint, applied to a wallet's public key. */
export function truncateAddress(address: string): string {
  return address.length <= 12 ? address : `${address.slice(0, 5)}…${address.slice(-5)}`;
}

function stringField(record: Record<string, unknown>, key: string): string | null {
  const value = record[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

function intField(record: Record<string, unknown>, key: string): number | null {
  const value = record[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** `LiveExecutorOut.policy` -- the five levers `docs/RISK_ENGINE_MEME.md` §3.1 names, as the executor's own heartbeat wrote them (`hunter_meme_executor/heartbeat.py`). An absent field is left out, never shown as zero. */
export function policyLines(policy: Record<string, unknown> | null | undefined): string[] {
  if (!policy) return ["tetos: sem leitura do executor"];
  const lines: string[] = [];
  const profile = stringField(policy, "profile");
  if (profile) lines.push(`perfil: ${profile}`);
  const wallet = stringField(policy, "wallet_max_sol");
  if (wallet) lines.push(`teto da carteira: ${formatSol(wallet)}`);
  const perTrade = stringField(policy, "max_sol_per_trade");
  if (perTrade) lines.push(`teto por compra: ${formatSol(perTrade)}`);
  const dailyCap = stringField(policy, "daily_loss_cap_sol");
  if (dailyCap) lines.push(`teto de perda diária: ${formatSol(dailyCap)}`);
  const maxOpen = intField(policy, "max_open_positions");
  if (maxOpen !== null) lines.push(`posições simultâneas: até ${maxOpen}`);
  const cooldown = intField(policy, "rug_cooldown_s");
  if (cooldown !== null) lines.push(`pausa após rug: ${cooldown} s`);
  return lines.length > 0 ? lines : ["tetos: nenhum campo reconhecido na leitura do executor"];
}

function readSmallTest(gates: Record<string, unknown>): Record<string, unknown> | null {
  const raw = gates.small_test;
  return raw !== null && typeof raw === "object" ? (raw as Record<string, unknown>) : null;
}

/** `gates.small_test` -- the owner's written test-pequeno authorization (`docs/ACTIVATION.md` §9b item 2), never inventing a bound the executor did not report. */
function smallTestLines(smallTest: Record<string, unknown>): string[] {
  const authorizedBy = stringField(smallTest, "authorized_by") ?? "não informado";
  const lines = [`Teste pequeno autorizado por ${authorizedBy}`];
  const maxPerTrade = stringField(smallTest, "max_sol_per_trade");
  if (maxPerTrade) lines.push(`até ${formatSol(maxPerTrade)} por compra`);
  const maxTotal = stringField(smallTest, "max_total_sol");
  if (maxTotal) lines.push(`até ${formatSol(maxTotal)} no total`);
  const maxTrades = intField(smallTest, "max_trades");
  if (maxTrades !== null) lines.push(`até ${maxTrades} compra(s)`);
  const expiresAt = stringField(smallTest, "expires_at");
  if (expiresAt) lines.push(`válido até ${formatBrasiliaShort(expiresAt) ?? expiresAt}`);
  const note = stringField(smallTest, "decision_note");
  if (note) lines.push(`decisão registrada: ${note}`);
  return lines;
}

/** `LiveExecutorOut.gates` -- Portões A/B vermelhos, o teste pequeno autorizado por escrito, ou os dois portões verdes; nunca inventa uma data que o executor não mandou. */
export function gatesLines(gates: Record<string, unknown> | null | undefined): string[] {
  if (!gates) return ["portões: sem leitura do executor"];
  if (gates.live !== true) return ["Portões A/B vermelhos — sem autorização para operar com dinheiro real"];
  const smallTest = readSmallTest(gates);
  if (smallTest) return smallTestLines(smallTest);
  const signedBy = stringField(gates, "signed_by") ?? "não informado";
  const validUntil = stringField(gates, "valid_until");
  return [`Portões A e B verdes, assinado por ${signedBy}${validUntil ? ` · válido até ${formatBrasiliaShort(validUntil) ?? validUntil}` : ""}`];
}

export interface KillSwitchSourceLine {
  key: "system" | "redis" | "file" | "wallet";
  label: string;
  value: string;
}

const SOURCE_LABEL: Record<KillSwitchSourceLine["key"], string> = {
  system: "sistema (SYSTEM_KILL_SWITCH)",
  redis: "Redis (meme:kill)",
  file: "arquivo (meme.kill)",
  wallet: "trava diária da carteira",
};

/** `LiveExecutorOut.kill_switch_sources` -- the four independent sources (§7), each read as the executor's own state string; `""` means the source itself has nothing to say (no file, no Redis key), never "ACTIVE" by assumption. */
export function killSwitchSourceLines(sources: Record<string, string>): KillSwitchSourceLine[] {
  return (["system", "redis", "file", "wallet"] as const).map((key) => ({ key, label: SOURCE_LABEL[key], value: sources[key] ?? "" }));
}
