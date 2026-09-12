"use client";

/**
 * Shared pieces of every REAL two-step confirmation on the desk (T4.17):
 * "Aprovar (REAL)" / "Registrar (REAL)" (`components/meme-desk/approve-real-sheet.tsx`,
 * `components/meme-desk/manual-buy-dialog.tsx`) and "Vender agora (REAL)"
 * (`live-positions-section.tsx`). Step (a) is a summary the operator cannot
 * miss -- ticker + mint, the four parameters, the caps that apply, and the
 * mainnet warning; step (b) is typing something back (the exact SOL size, or
 * the word "VENDER") before the red button unlocks. Lives in `meme-live` (not
 * `meme-desk`) so the dependency is one-directional: `meme-desk` may import
 * from `meme-live`, never the other way.
 */
import { formatSol } from "@/components/meme/meme-format";
import { Input } from "@/components/ui/input";
import type { LiveExecutor } from "@/lib/api/meme-live-types";
import { compareDecimalStrings } from "@/lib/format";

import { policyLines } from "./live-format";

export function RealBadge() {
  return <span className="rounded-md bg-red-soft px-1.5 py-0.5 text-[11px] font-semibold text-red">REAL</span>;
}

export const MAINNET_WARNING = "Isto assina uma transação real na mainnet.";

export interface RealSummaryProps {
  /** "bum bum (BAM) · Fh42k…u5pump" -- ticker (or a named fallback) plus the shortened mint, contract §1. */
  tickerLine: string;
  sizeSol: string;
  targetX: string;
  trailingPct: string;
  maxHoldS: string;
  /** `null` when the executor's own heartbeat carried no policy (an honest "sem leitura" line, never an invented number). */
  executor: LiveExecutor | null;
}

/** Step (a): the four parameters, the caps that apply (the executor's own policy -- the engine applies the smallest of these plus the small-test scope at order time), and the mainnet warning. */
export function RealSummary({ tickerLine, sizeSol, targetX, trailingPct, maxHoldS, executor }: RealSummaryProps) {
  return (
    <div className="flex flex-col gap-2 rounded-md border border-red/40 bg-red-soft/20 p-3 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <RealBadge />
        <span className="font-medium text-fg">{tickerLine}</span>
      </div>
      <p className="font-mono tabular-nums text-fg">
        {sizeSol ? formatSol(sizeSol) : "tamanho não informado"} · alvo {targetX || "?"}× · trailing {trailingPct || "?"}% · espera {maxHoldS || "?"} s
      </p>
      <div className="text-fg-muted">
        <p className="font-medium text-fg-muted">Tetos que se aplicam (o motor aplica o menor entre eles):</p>
        <ul className="list-disc pl-4">
          {policyLines(executor?.policy ?? null).map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </div>
      <p className="font-semibold text-red">{MAINNET_WARNING}</p>
    </div>
  );
}

/** `true` only when `typed` is a well-formed decimal numerically equal to `expected` -- `compareDecimalStrings` (never `Number()`, the values are money) tolerates "0.020" for "0.02" while still requiring the operator to actually type the right number. */
export function sizeMatches(expected: string, typed: string): boolean {
  const trimmed = typed.trim();
  if (!/^\d+(\.\d+)?$/.test(trimmed) || expected.trim() === "") return false;
  try {
    return compareDecimalStrings(trimmed, expected) === 0;
  } catch {
    return false;
  }
}

export interface SizeMatchFieldProps {
  id: string;
  expected: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

/** Step (b) of an approval: "digite o tamanho em SOL exatamente" -- the field that gates the red button. */
export function SizeMatchField({ id, expected, value, onChange, disabled = false }: SizeMatchFieldProps) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-xs font-medium text-fg-muted">
        Digite o tamanho em SOL para liberar o envio (ex.: {expected || "0.02"})
      </label>
      <Input
        id={id}
        type="text"
        inputMode="decimal"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className="w-full font-mono tabular-nums"
        placeholder={expected}
      />
    </div>
  );
}

/** `true` only when `typed` (trimmed, case-insensitive) equals `word` -- "VENDER" on a real sell-now. */
export function wordMatches(word: string, typed: string): boolean {
  return typed.trim().toUpperCase() === word;
}

export interface WordMatchFieldProps {
  id: string;
  word: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

/** Step (b) of a sell-now: typing the word back unlocks the red confirm button. */
export function WordMatchField({ id, word, label, value, onChange, disabled = false }: WordMatchFieldProps) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-xs font-medium text-fg-muted">
        {label}
      </label>
      <Input id={id} type="text" value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled} className="w-full font-mono uppercase" placeholder={word} />
    </div>
  );
}
