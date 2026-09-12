/**
 * Client- and server-safe validation for the desk's approval sheet and the
 * manual buy form (T4.7). No `"server-only"` on purpose -- the sheet runs
 * this in the browser for inline errors before ever calling a Server
 * Action (same convention as `lib/api/manual-order-form-schema.ts`).
 *
 * Bounds mirror `hunter_api.schemas.meme_desk.DeskParamsIn`, which mirrors
 * `hunter_indicators.meme.rules.ExitRules`: size > 0, target > 1×, trailing
 * in (0, 100) %, hold >= 1 s. Comparisons use `compareDecimalStrings`
 * (`lib/format.ts`), never `Number()` -- the values are money. zod v4 keeps
 * running refinements after a failed `regex`, so every comparison is
 * guarded by the same pattern first (a comma decimal must fail on the
 * pattern's message, never throw inside the comparison).
 */
import { z } from "zod";

import { compareDecimalStrings } from "@/lib/format";

import type { MemeDeskApproveBody, MemeDeskManualBody, MemeDeskParams } from "./meme-desk-types";

const DECIMAL_PATTERN = /^\d+(\.\d+)?$/;
const INTEGER_PATTERN = /^\d+$/;
export const MAX_NOTE_LENGTH = 500;
export const MIN_MINT_LENGTH = 32;
export const MAX_MINT_LENGTH = 64;

const decimalString = z.string().trim().regex(DECIMAL_PATTERN, "Use um número decimal com ponto, ex.: 0.25.");

/** `true` when `value` is a well-formed decimal and `predicate(compare)` holds -- a malformed value already failed the pattern, so it passes here to avoid a second, confusing message. */
function decimalCheck(value: string, predicate: (compare: (floor: string) => number) => boolean): boolean {
  if (!DECIMAL_PATTERN.test(value.trim())) return true;
  return predicate((floor) => compareDecimalStrings(value, floor));
}

export const deskParamsFormSchema = z.object({
  sizeSol: decimalString.refine((v) => decimalCheck(v, (cmp) => cmp("0") > 0), "O tamanho em SOL deve ser maior que zero."),
  targetX: decimalString.refine((v) => decimalCheck(v, (cmp) => cmp("1") > 0), "O alvo deve ser maior que 1×."),
  trailingPct: decimalString.refine((v) => decimalCheck(v, (cmp) => cmp("0") > 0 && cmp("100") < 0), "O trailing deve ficar entre 0 e 100 %."),
  maxHoldS: z
    .string()
    .trim()
    .regex(INTEGER_PATTERN, "A espera máxima é em segundos inteiros.")
    .refine((v) => !INTEGER_PATTERN.test(v.trim()) || compareDecimalStrings(v, "1") >= 0, "A espera máxima deve ser de pelo menos 1 s."),
  note: z.string().trim().max(MAX_NOTE_LENGTH, `A nota tem no máximo ${MAX_NOTE_LENGTH} caracteres.`),
});
export type DeskParamsFormValues = z.infer<typeof deskParamsFormSchema>;

export const manualBuyFormSchema = deskParamsFormSchema.extend({
  mint: z
    .string()
    .trim()
    .min(MIN_MINT_LENGTH, `O mint tem pelo menos ${MIN_MINT_LENGTH} caracteres.`)
    .max(MAX_MINT_LENGTH, `O mint tem no máximo ${MAX_MINT_LENGTH} caracteres.`),
});
export type ManualBuyFormValues = z.infer<typeof manualBuyFormSchema>;

/** The sheet's initial values: the loop's `suggested` (contract §Tela, "pré-preenchidos com `suggested`, editáveis"); a missing suggestion is an empty field, never an invented default. */
export function formValuesFromSuggested(suggested: MemeDeskParams | null | undefined): DeskParamsFormValues {
  return {
    sizeSol: suggested?.size_sol ?? "",
    targetX: suggested?.target_x ?? "",
    trailingPct: suggested?.trailing_pct ?? "",
    maxHoldS: suggested?.max_hold_s === null || suggested?.max_hold_s === undefined ? "" : String(suggested.max_hold_s),
    note: "",
  };
}

export function toApproveBody(values: DeskParamsFormValues): MemeDeskApproveBody {
  return {
    size_sol: values.sizeSol,
    target_x: values.targetX,
    trailing_pct: values.trailingPct,
    max_hold_s: Number.parseInt(values.maxHoldS, 10),
    note: values.note === "" ? null : values.note,
    // T4.14: the desk only files PAPER proposals until the live executor exists and
    // `ENABLE_MEME_LIVE_TRADING` is on; "Aprovar (REAL)" is a separate, double-confirmed path.
    mode: "paper",
  };
}

export function toManualBody(values: ManualBuyFormValues): MemeDeskManualBody {
  return { ...toApproveBody(values), mint: values.mint };
}

/** First zod issue as one sentence, for the inline error line. */
export function firstIssueMessage(error: z.ZodError): string {
  return error.issues[0]?.message ?? "Dados inválidos.";
}
