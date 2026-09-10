/**
 * Wallet-specific formatting and reason vocabulary (docs/DESIGN.md §1/§2:
 * tabular-nums, explicit sign, semantic color, honest nulls). A `null` value
 * here always carries a named reason from the API -- CLAUDE.md's "`null`
 * never vira 0" -- so every helper below renders that reason as readable
 * Portuguese text instead of a dash or a silent zero.
 */
import { formatPct } from "@/lib/format";

/** `PortfolioSummaryOut.unavailable[]` codes -- `hunter_core.portfolio.state.build_portfolio_state` (Python docstring quoted in `schemas/portfolio.py`). */
const UNAVAILABLE_LABELS: Record<string, string> = {
  marks: "marcações de alguma posição aberta estão desatualizadas",
  market_identity: "identidade de mercado incompleta para uma posição ou reserva (ex.: β ainda não validado)",
  daily_reference: "a referência do dia (abertura em Brasília) não pôde ser reconstruída -- perda diária não é mensurável agora",
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

/**
 * `RiskLimitsPresetOut` (T3.72d): the sentence for the wallet's own Risk
 * profile banner and, unchanged, for the "Nova ordem paper" gate -- one
 * function, both call sites, so the two never drift apart.
 *
 * `/risk-limits` does not carry the execution-worker's own
 * `risk_profile_missing`/`risk_profile_invalid`/`risk_profile_diverged`
 * reason (`hunter_execution_worker.risk_profile`, T3.69b); only
 * `preset.source` and `preset.diverged_from_engine` travel over the wire.
 * `diverged_from_engine` alone already covers both `_invalid` (forced
 * `true` with `source="engine_default"`, an unreadable row) and
 * `_diverged` (`source="risk_profile"`, a row that validates but differs
 * from `PAPER_V1`); `source !== "risk_profile"` with the flag `false` is
 * the third case, `_missing` (no `risk_profile_id` at all) -- the proxy
 * this task's brief allows in the absence of a dedicated reason field.
 */
const RISK_PROFILE_DIVERGED_MESSAGE =
  "Os limites mostrados não são os que o motor aplica -- perfil divergente; procedimento no ACTIVATION.md §8b.";
const RISK_PROFILE_MISSING_MESSAGE =
  "Carteira sem perfil de risco vinculado -- o motor não admite entradas até o vínculo (ACTIVATION.md §8b).";

export function riskProfileGateReason(preset: { source: string; diverged_from_engine: boolean }): string | null {
  if (preset.diverged_from_engine) return RISK_PROFILE_DIVERGED_MESSAGE;
  if (preset.source !== "risk_profile") return RISK_PROFILE_MISSING_MESSAGE;
  return null;
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
