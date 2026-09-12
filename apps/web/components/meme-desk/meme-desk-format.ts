/**
 * Pure helpers for the operator desk (T4.7): partitioning the desk into its
 * sections, countdowns, remaining hold, SOL -> US$ at the observed quote,
 * and the loop's honest state. No React, no fetch -- `tests/meme-desk-format.test.ts`.
 *
 * Money stays a decimal string end to end: the one multiplication here
 * (`multiplyDecimalStrings`) is `BigInt` arithmetic, never a float.
 */
import { formatSol } from "@/components/meme/meme-format";
import type { MemeDeskRow, MemeLoopState } from "@/lib/api/meme-desk-types";
import { formatMoney } from "@/lib/format";
import { formatBrasiliaDate, formatBrasiliaShort } from "@/lib/time";

export interface DeskPartition {
  /** `proposed` -- awaiting the operator's approval (countdown to `expires_at`). */
  proposals: MemeDeskRow[];
  /** `approved` with no bet yet -- the loop fills on the next snapshot. */
  awaitingFill: MemeDeskRow[];
  /** A bet the loop opened and has not closed. */
  open: MemeDeskRow[];
  /** A bet closed on today's Brasília day. */
  closedToday: MemeDeskRow[];
  /** Everything else: rejected/expired/unfilled proposals and older closes. */
  recent: MemeDeskRow[];
}

export function partitionDesk(rows: readonly MemeDeskRow[], nowIso: string): DeskPartition {
  const today = formatBrasiliaDate(nowIso);
  const out: DeskPartition = { proposals: [], awaitingFill: [], open: [], closedToday: [], recent: [] };
  for (const row of rows) {
    if (row.status === "proposed") out.proposals.push(row);
    else if (row.status === "approved" && !row.bet) out.awaitingFill.push(row);
    else if (row.bet?.status === "open") out.open.push(row);
    else if (row.bet?.status === "closed" && row.bet.exit_at && formatBrasiliaDate(row.bet.exit_at) === today) out.closedToday.push(row);
    else out.recent.push(row);
  }
  return out;
}

/** "45 s", "1 min 32 s", "2 h 05 min" -- always with a space before the unit (DESIGN-5). */
export function formatDuration(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  if (totalSeconds < 60) return `${totalSeconds} s`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes < 60) return `${minutes} min ${seconds} s`;
  const hours = Math.floor(minutes / 60);
  return `${hours} h ${String(minutes % 60).padStart(2, "0")} min`;
}

/** Countdown to `expires_at` (contract §Tela). Past the deadline it says so -- the loop stamps `expired` on its own tick, and the row may still read `proposed` until then. */
export function countdownLabel(expiresAtIso: string, nowMs: number): string {
  const deadline = new Date(expiresAtIso).getTime();
  if (Number.isNaN(deadline)) return "prazo desconhecido";
  const remaining = deadline - nowMs;
  if (remaining <= 0) return `expirou há ${formatDuration(-remaining)}`;
  return `expira em ${formatDuration(remaining)}`;
}

/** Remaining hold of an open bet against `entry_at + max_hold_s`; `null` deadline means the loop wrote no `max_hold_s` -- said, never guessed. */
export function remainingHoldLabel(deadlineIso: string | null | undefined, nowMs: number): string {
  if (!deadlineIso) return "espera máxima não informada";
  const deadline = new Date(deadlineIso).getTime();
  if (Number.isNaN(deadline)) return "espera máxima não informada";
  const remaining = deadline - nowMs;
  if (remaining <= 0) return `espera vencida há ${formatDuration(-remaining)} — fecha na próxima fotografia`;
  return `espera restante ${formatDuration(remaining)}`;
}

function splitDecimal(value: string): { negative: boolean; digits: string; scale: number } {
  const match = /^([+-])?(\d+)(?:\.(\d+))?$/.exec(value.trim());
  if (!match) throw new TypeError(`Invalid decimal value: ${JSON.stringify(value)}`);
  const [, sign, intPart, fracPart = ""] = match;
  return { negative: sign === "-", digits: `${intPart ?? "0"}${fracPart}`, scale: fracPart.length };
}

/** Exact product of two decimal strings (`BigInt`), e.g. "4.98" × "181" = "901.38". */
export function multiplyDecimalStrings(a: string, b: string): string {
  const pa = splitDecimal(a);
  const pb = splitDecimal(b);
  const product = BigInt(pa.digits) * BigInt(pb.digits);
  const scale = pa.scale + pb.scale;
  const negative = pa.negative !== pb.negative && product !== 0n;
  const raw = product.toString().padStart(scale + 1, "0");
  const intDigits = raw.slice(0, raw.length - scale) || "0";
  const fracDigits = raw.slice(raw.length - scale);
  const text = scale > 0 ? `${intDigits}.${fracDigits}` : intDigits;
  return `${negative ? "-" : ""}${text}`;
}

/** SOL amount at the observed SOL/USD quote, as "US$ 901.38" -- the caller says when the quote was observed; this never claims a live rate. */
export function solToUsd(sol: string, rate: string): string {
  return `US$ ${formatMoney(multiplyDecimalStrings(sol, rate), { currency: "USD", decimals: 2 }).replace(/[^0-9.,-]/g, "")}`;
}

function isZero(value: string): boolean {
  return /^[+-]?0+(\.0+)?$/.test(value.trim());
}

/** "+0.1800 SOL" / "-0.0200 SOL" / "0 SOL" (DESIGN.md §2: explicit sign). */
export function formatSolSigned(value: string, decimals = 4): string {
  const negative = value.trim().startsWith("-");
  const sign = isZero(value) || negative ? "" : "+";
  return `${sign}${formatSol(value, decimals)}`;
}

/** Semantic color for a signed amount (DESIGN.md §2: green/red only with meaning; zero is neutral). */
export function signClass(value: string | null | undefined): string {
  if (!value || isZero(value)) return "text-fg-muted";
  return value.trim().startsWith("-") ? "text-red" : "text-green";
}

/** "2.00×" -- a multiple, two decimals, decimal-safe. */
export function formatMultiple(value: string): string {
  return `${formatMoney(value, { currency: "USD", decimals: 2 }).replace(/[^0-9.,-]/g, "")}×`;
}

/** "0.90 R" -- an R multiple (PnL / initial risk), two decimals. */
export function formatR(value: string): string {
  return `${formatMoney(value, { currency: "USD", decimals: 2 }).replace(/[^0-9.,-]/g, "")} R`;
}

export type LoopTone = "alive" | "stopped" | "unknown";

export interface LoopStateLabel {
  tone: LoopTone;
  label: string;
}

/** Contract §Semântica 5 / §Tela: "laço vivo" ≠ "laço parado desde …" ≠ "sem leitura". `staleAfterMs` = three loop ticks (one per minute) missed. */
export function loopStateLabel(loop: MemeLoopState, nowMs: number, staleAfterMs = 180_000): LoopStateLabel {
  if (!loop.lastTickAt) {
    const why =
      loop.reason === "endpoint_missing"
        ? "o placar do laço ainda não responde"
        : loop.reason === "read_failed"
          ? "falha ao consultar o placar do laço"
          : loop.reason === "shape_unknown"
            ? "o placar não trouxe o carimbo do último tick"
            : "sem carimbo do último tick";
    return { tone: "unknown", label: `laço: sem leitura (${why})` };
  }
  const tick = new Date(loop.lastTickAt).getTime();
  if (Number.isNaN(tick)) return { tone: "unknown", label: "laço: sem leitura (carimbo ilegível)" };
  const age = nowMs - tick;
  if (age > staleAfterMs) return { tone: "stopped", label: `laço parado desde ${formatBrasiliaShort(loop.lastTickAt) ?? "--"}` };
  return { tone: "alive", label: `laço vivo · último tick há ${formatDuration(Math.max(0, age))}` };
}

/** Minutes since the newest `proposed_at` on the desk, or `null` when the desk has never seen a proposal. */
export function minutesSinceNewestProposal(rows: readonly MemeDeskRow[], nowMs: number): number | null {
  let newest = Number.NEGATIVE_INFINITY;
  for (const row of rows) {
    const at = new Date(row.proposed_at).getTime();
    if (!Number.isNaN(at) && at > newest) newest = at;
  }
  if (newest === Number.NEGATIVE_INFINITY) return null;
  return Math.max(0, Math.floor((nowMs - newest) / 60_000));
}

/** The honest empty state of "Propostas" (contract §Tela): three different sentences for three different facts. */
export function emptyProposalsLabel(loop: LoopStateLabel, minutesSinceNewest: number | null): string {
  if (loop.tone === "alive") {
    return minutesSinceNewest === null
      ? "nenhuma proposta registrada ainda (laço vivo)"
      : `nenhuma proposta nos últimos ${minutesSinceNewest} min (laço vivo)`;
  }
  if (loop.tone === "stopped") return `${loop.label} — nenhuma proposta nova chega enquanto o laço não roda`;
  return "nenhuma proposta em espera — sem leitura do laço, não dá para dizer se falta proposta ou se o laço parou";
}
