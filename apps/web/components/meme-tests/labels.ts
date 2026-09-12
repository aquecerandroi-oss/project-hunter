/**
 * Test-record vocabulary (T4.13; DESIGN-5 "sem backstage na copy": no enum
 * value reaches the screen raw). `Record<Enum, string>` makes the compiler
 * enforce completeness for the unions `lib/api/meme-tests-types.ts` names;
 * `tests/meme-tests-labels.test.ts` iterates the same arrays for a second,
 * explicit exhaustiveness check (the `components/meme-desk/labels.ts`
 * convention -- a missing label broke the production build three times on
 * 2026-09-12).
 */
import { MEME_LAB_CONTEXT_REASONS, MEME_PNL_USD_BASES, MEME_PNL_USD_REASONS, MEME_TEST_KINDS, MEME_WALLETS_SOURCES, type MemeLabContextReason, type MemePnlUsdBasis, type MemePnlUsdReason, type MemeTestKind, type MemeWalletsSource } from "@/lib/api/meme-tests-types";

const KIND_LABEL: Record<MemeTestKind, string> = {
  paper: "PAPEL",
  real_observed: "REAL — observado na cadeia",
};

export function testKindLabel(kind: string): string {
  return (MEME_TEST_KINDS as readonly string[]).includes(kind) ? KIND_LABEL[kind as MemeTestKind] : "tipo não previsto";
}

const WALLETS_SOURCE_LABEL: Record<MemeWalletsSource, string> = {
  observada: "carteira observada na cadeia",
  "não observada": "sem carteira observada ainda",
  "leitura indisponível": "carteira observada, mas a leitura das posições falhou",
};

export function walletsSourceLabel(source: string): string {
  return (MEME_WALLETS_SOURCES as readonly string[]).includes(source) ? WALLETS_SOURCE_LABEL[source as MemeWalletsSource] : "estado da carteira não previsto";
}

const PNL_USD_BASIS_LABEL: Record<MemePnlUsdBasis, string> = {
  exit_quote: "cotação SOL/USD observada na saída",
  entry_quote_provisional: "provisório — cotação observada na entrada",
};

export function pnlUsdBasisLabel(basis: string | null | undefined): string | null {
  if (!basis) return null;
  return (MEME_PNL_USD_BASES as readonly string[]).includes(basis) ? PNL_USD_BASIS_LABEL[basis as MemePnlUsdBasis] : "base não prevista";
}

const PNL_USD_REASON_LABEL: Record<MemePnlUsdReason, string> = {
  no_exit_quote: "sem cotação SOL/USD na saída",
  no_entry_quote: "sem cotação SOL/USD na entrada",
  no_pnl: "sem resultado ainda",
};

export function pnlUsdReasonLabel(reason: string | null | undefined): string {
  if (!reason) return "sem US$ registrado";
  return (MEME_PNL_USD_REASONS as readonly string[]).includes(reason) ? PNL_USD_REASON_LABEL[reason as MemePnlUsdReason] : "motivo não previsto";
}

const LAB_CONTEXT_REASON_LABEL: Record<MemeLabContextReason, string> = {
  manual_no_minute: "compra manual — não nasceu de um minuto do Lab",
  no_features_row: "o Lab não tem a linha desse minuto",
};

export function labContextReasonLabel(reason: string | null | undefined): string | null {
  if (!reason) return null;
  return (MEME_LAB_CONTEXT_REASONS as readonly string[]).includes(reason) ? LAB_CONTEXT_REASON_LABEL[reason as MemeLabContextReason] : "contexto não previsto";
}

/** `meme_features_1m.line_reason` (0026) -- why no support line could be drawn that minute. */
const LINE_REASON_LABEL: Record<string, string> = {
  too_few_points: "menos de 5 fotografias na janela",
  no_snapshot: "sem fotografia do minuto",
  flat: "sem dois fundos locais",
  out_of_range: "valor fora do alcance da coluna",
};

export function lineReasonLabel(reason: string | null | undefined): string {
  if (!reason) return "sem motivo registrado";
  return LINE_REASON_LABEL[reason] ?? `motivo: ${reason}`;
}

const STATUS_LABEL: Record<string, string> = { open: "aberta", closed: "fechada" };

export function testStatusLabel(status: string): string {
  return STATUS_LABEL[status] ?? "estado não previsto";
}

/** `sim`/`não`/the honest absence -- the same three words the CSV writes. */
export function yesNoLabel(value: boolean | null | undefined, absent = "sem leitura"): string {
  if (value === null || value === undefined) return absent;
  return value ? "sim" : "não";
}
