import { z } from "zod";

/**
 * Client- and server-safe validation for everything the onboarding wizard
 * and the settings forms submit. No `"server-only"` here on purpose: the
 * wizard (components/onboarding/**) runs these in the browser for inline
 * errors, and the matching Server Action re-runs the same schema before
 * ever calling `apiFetch` (docs/ARCHITECTURE.md §9 -- the API is the source
 * of truth, this is defense in depth plus fast feedback, never a substitute
 * for the API's own validation).
 *
 * Mirrors `apps/api/hunter_api/schemas/{organizations,workspaces,invitations}.py`
 * field-for-field; keep the two in sync by hand (T09 does not touch `apps/api`).
 */

// ---- workspaces.py: MIN_VIRTUAL_CAPITAL / MAX_MONITORED_EXCHANGES ----
export const MIN_VIRTUAL_CAPITAL = 1000;
export const CAPITAL_PRESETS = [10_000, 25_000, 50_000, 100_000] as const;
export const MAX_MONITORED_EXCHANGES = 10;

/**
 * The exchanges onboarding can offer to monitor. M0 has no `/exchanges`
 * listing endpoint (docs/ARCHITECTURE.md §7's `markets` router doesn't land
 * until M1) -- these are the two codes `infra/scripts/seed.py` actually
 * inserts, hardcoded here on purpose. `complete_onboarding` (services/workspaces.py)
 * validates against the real seeded set server-side, so a drift here would
 * surface as a 422 on submit rather than silently persisting a bad code.
 */
export const EXCHANGE_CODES = ["binance", "bybit"] as const;
export const EXCHANGE_LABELS: Record<(typeof EXCHANGE_CODES)[number], string> = {
  binance: "Binance",
  bybit: "Bybit",
};

export const OBJECTIVES = ["explore", "paper_trading", "research", "automated_trading"] as const;
export type Objective = (typeof OBJECTIVES)[number];

export const RISK_PRESETS = ["conservative", "balanced", "aggressive", "custom"] as const;
export type RiskPresetValue = (typeof RISK_PRESETS)[number];

export const ORG_ROLES = ["OWNER", "ADMIN", "TRADER", "ANALYST", "VIEWER"] as const;

/** docs/RISK_ENGINE.md §2 -- shown read-only at onboarding step 4 and in Settings. */
export const RISK_LIMITS_TABLE: {
  key: string;
  label: string;
  conservative: string;
  balanced: string;
  aggressive: string;
}[] = [
  { key: "max_position_pct", label: "Tamanho máx. por posição", conservative: "2%", balanced: "5%", aggressive: "10%" },
  { key: "risk_per_trade_pct", label: "Risco por trade", conservative: "0.25%", balanced: "0.5%", aggressive: "1%" },
  { key: "max_total_exposure_pct", label: "Exposição total máx.", conservative: "30%", balanced: "60%", aggressive: "100%" },
  { key: "max_daily_loss_pct", label: "Perda diária máx.", conservative: "1%", balanced: "2%", aggressive: "4%" },
  { key: "max_drawdown_pct", label: "Drawdown máx.", conservative: "5%", balanced: "10%", aggressive: "20%" },
  { key: "max_concurrent_positions", label: "Posições simultâneas máx.", conservative: "3", balanced: "6", aggressive: "12" },
  { key: "max_leverage", label: "Alavancagem máx.", conservative: "1x", balanced: "2x", aggressive: "3x" },
];

export const organizationNameSchema = z.string().trim().min(1, "Obrigatório").max(120);
export const workspaceNameSchema = z.string().trim().min(1, "Obrigatório").max(120).nullable().optional();

export const objectiveSchema = z.enum(OBJECTIVES);

export const virtualCapitalSchema = z
  .string()
  .trim()
  .regex(/^\d+(\.\d+)?$/, "Use apenas números (ex.: 10000 ou 10000.50)")
  .refine((value) => Number(value) >= MIN_VIRTUAL_CAPITAL, `O capital virtual mínimo é ${MIN_VIRTUAL_CAPITAL}`);

export const riskPresetSchema = z.enum(RISK_PRESETS);

export const monitoredExchangesSchema = z
  .array(z.enum(EXCHANGE_CODES))
  .max(MAX_MONITORED_EXCHANGES, `No máximo ${MAX_MONITORED_EXCHANGES} exchanges`);

export const onboardingCreateOrgSchema = z.object({
  name: organizationNameSchema,
  workspaceName: workspaceNameSchema,
});

export const onboardingUpdateSchema = z.object({
  objective: objectiveSchema,
  virtualCapital: virtualCapitalSchema,
  riskPreset: riskPresetSchema,
  monitoredExchanges: monitoredExchangesSchema,
});

export const memberRoleSchema = z.enum(ORG_ROLES);

export const invitationEmailSchema = z
  .string()
  .trim()
  .toLowerCase()
  .regex(/^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$/, "Email inválido");

export const invitationCreateSchema = z.object({
  email: invitationEmailSchema,
  role: memberRoleSchema,
});

export type OnboardingCreateOrgInput = z.infer<typeof onboardingCreateOrgSchema>;
export type OnboardingUpdateInput = z.infer<typeof onboardingUpdateSchema>;
export type InvitationCreateInput = z.infer<typeof invitationCreateSchema>;
