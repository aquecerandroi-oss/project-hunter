/**
 * Wallet-specific formatting and reason vocabulary (docs/DESIGN.md §1/§2:
 * tabular-nums, explicit sign, semantic color, honest nulls). A `null` value
 * here always carries a named reason from the API -- CLAUDE.md's "`null`
 * never vira 0" -- so every helper below renders that reason as readable
 * Portuguese text instead of a dash or a silent zero.
 */
import { formatMoney, formatPct } from "@/lib/format";

/**
 * BRL amounts always use `locale: "en-US"` (never `"pt-BR"`) -- `formatMoney`
 * always joins the grouped integer and fraction with a literal ".", but
 * `Intl.NumberFormat("pt-BR")` groups thousands with "." too, which would
 * collide into an ambiguous "R$100.000.00". `Intl`'s BRL currency symbol
 * ("R$") renders correctly under "en-US" regardless of that locale's own
 * grouping convention, so this sidesteps the collision instead of touching
 * `formatMoney`'s shared grouping logic for every other caller.
 */
export function formatBrl(value: string | number): string {
  return formatMoney(value, { currency: "BRL" });
}

/** `formatBrl` with an explicit leading "+" on a non-zero, non-negative amount (docs/DESIGN.md §2: signed numbers) -- `formatMoney` already prints "-" for negatives but never "+" for positives. */
export function formatBrlSigned(value: string | number): string {
  const raw = typeof value === "number" ? value.toString() : value;
  const isZero = /^[+-]?0+(\.0+)?$/.test(raw.trim());
  const negative = raw.trim().startsWith("-");
  const sign = isZero || negative ? "" : "+";
  return `${sign}${formatBrl(value)}`;
}

/** `PortfolioSummaryOut.unavailable[]` codes -- `hunter_core.portfolio.state.build_portfolio_state` (Python docstring quoted in `schemas/portfolio.py`). */
const UNAVAILABLE_LABELS: Record<string, string> = {
  marks: "marcações de alguma posição aberta estão desatualizadas",
  market_identity: "identidade de mercado incompleta para uma posição ou reserva (ex.: β ainda não validado)",
  daily_reference: "a referência do dia (abertura em America/Sao_Paulo) não pôde ser reconstruída -- perda diária não é mensurável agora",
  daily_decomposition: "decomposição diária (realizado, não realizado e custos) indisponível",
};

/** Human label for an `unavailable` code, never dropping an unrecognized one silently. */
export function unavailableLabel(code: string): string {
  return UNAVAILABLE_LABELS[code] ?? `motivo não catalogado: ${code}`;
}

/** `PortfolioSummaryOut.brl_unavailable_reason` -- `services/portfolio_queries.py::_brl_reading`. */
const BRL_REASON_LABELS: Record<string, string> = {
  no_fx_observation: "nenhuma cotação USDT/BRL disponível ainda",
  fx_rejected: "a cotação mais recente foi recusada pela política de câmbio",
};

export function brlUnavailableLabel(reason: string): string {
  return BRL_REASON_LABELS[reason] ?? `motivo não catalogado: ${reason}`;
}

/** Semantic color for a signed decimal string -- neutral when the value is absent or exactly zero (a flat result is not a gain), never colored as if it were a real number. */
export function signColorClass(value: string | null): string {
  if (value === null) return "text-fg-muted";
  const trimmed = value.trim();
  if (/^-?0(\.0+)?$/.test(trimmed)) return "text-fg";
  return trimmed.startsWith("-") ? "text-red" : "text-green";
}

/** A percentage that is `null` exactly when the API could not compute it -- renders "indisponível" plus, when given, the fact that explains why. */
export function formatPctOrUnavailable(value: string | null, unavailableNote?: string): { text: string; isValue: boolean } {
  if (value !== null) return { text: formatPct(value), isValue: true };
  return { text: unavailableNote ? `indisponível (${unavailableNote})` : "indisponível", isValue: false };
}

const KILL_SWITCH_LABELS: Record<string, string> = {
  ACTIVE: "ATIVO",
  WARNING: "AVISO",
  TRADING_DISABLED: "BLOQUEADO",
  EMERGENCY: "EMERGÊNCIA",
};

export function killSwitchLabel(state: string): string {
  return KILL_SWITCH_LABELS[state] ?? state;
}

/** Badge color per docs/DESIGN.md §1 (`--color-warning` for WARNING, `--color-red` for the two blocking states). */
export function killSwitchBadgeVariant(state: string): "default" | "warning" | "negative" {
  if (state === "WARNING") return "warning";
  if (state === "TRADING_DISABLED" || state === "EMERGENCY") return "negative";
  return "default";
}
