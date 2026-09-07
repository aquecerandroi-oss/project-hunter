/**
 * `hb:execution:paper` formatting (T3.8c) -- a domain-local copy of the
 * kill-switch vocabulary, not an import of
 * `components/portfolio/portfolio-format.ts`: this repo keeps small
 * per-screen formatting helpers duplicated rather than shared across
 * domains (see `components/system/system-as-of.tsx`'s docstring for the
 * same reasoning, applied there to `LabAsOf`/`PortfolioAsOf`).
 */

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

/** A gauge already expressed in seconds (`protection_delay_s`) -- one decimal, never a bare rounded integer that would hide a sub-second delay a 5s readiness threshold cares about. */
export function formatSeconds(value: number): string {
  return `${value.toFixed(1)}s`;
}
