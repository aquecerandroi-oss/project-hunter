import type { Objective, RiskPresetValue } from "@/lib/api/schemas";
import type { WizardStep } from "@/components/onboarding/wizard-state";

/** Step titles for the progress indicator (docs/PRODUCT.md §3). */
export const STEP_LABELS: Record<WizardStep, string> = {
  1: "Organização",
  2: "Objetivo",
  3: "Capital",
  4: "Perfil de risco",
  5: "Exchanges",
  6: "Resumo",
};

export const OBJECTIVE_LABELS: Record<Objective, { title: string; description: string }> = {
  explore: { title: "Explorar", description: "Conhecer o produto sem compromisso com um fluxo específico." },
  paper_trading: { title: "Paper Trading", description: "Operar com capital virtual para testar decisões sem risco real." },
  research: { title: "Pesquisa", description: "Analisar mercados, anomalias e oportunidades sem operar." },
  automated_trading: {
    title: "Trading Automatizado",
    description: "Agentes propõem entradas sob o Risk Engine. Negociação ao vivo fica desabilitada até a Fase 4 — este objetivo hoje opera apenas em paper/shadow.",
  },
};

export const RISK_PRESET_LABELS: Record<RiskPresetValue, string> = {
  conservative: "Conservador",
  balanced: "Balanceado",
  aggressive: "Agressivo",
  custom: "Customizado",
};
