import { Badge } from "@/components/ui/badge";
import { EXCHANGE_LABELS } from "@/lib/api/schemas";
import type { WorkspaceOut } from "@/lib/api/types";
import { formatMoney } from "@/lib/format";

export interface WorkspaceCardProps {
  workspace: WorkspaceOut;
}

const OBJECTIVE_LABELS: Record<WorkspaceOut["objective"], string> = {
  explore: "Explorar",
  paper_trading: "Paper Trading",
  research: "Pesquisa",
  automated_trading: "Trading Automatizado",
};

/**
 * The onboarding answers, read back from `settings` JSONB
 * (apps/api/hunter_api/services/workspaces.py: `default_initial_capital`,
 * `monitored_exchanges`, `risk_preset` -- no dedicated columns in M0).
 */
function readSettings(settings: WorkspaceOut["settings"]): {
  capital: string | null;
  riskPreset: string | null;
  exchanges: string[];
} {
  const capital = typeof settings.default_initial_capital === "string" ? settings.default_initial_capital : null;
  const riskPreset = typeof settings.risk_preset === "string" ? settings.risk_preset : null;
  const exchanges = Array.isArray(settings.monitored_exchanges)
    ? settings.monitored_exchanges.filter((e): e is string => typeof e === "string")
    : [];
  return { capital, riskPreset, exchanges };
}

export function WorkspaceCard({ workspace }: WorkspaceCardProps) {
  const { capital, riskPreset, exchanges } = readSettings(workspace.settings);

  return (
    <section className="rounded-lg border border-border bg-surface-1 p-4">
      <h2 className="text-sm font-medium text-muted">Workspace</h2>
      <p className="mt-1 text-lg font-semibold text-foreground">{workspace.name}</p>
      <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="text-muted">Objetivo</dt>
          <dd className="text-foreground">{OBJECTIVE_LABELS[workspace.objective]}</dd>
        </div>
        <div>
          <dt className="text-muted">Capital virtual</dt>
          <dd className="num text-foreground">{capital ? formatMoney(capital) : "--"}</dd>
        </div>
        <div>
          <dt className="text-muted">Perfil de risco</dt>
          <dd className="text-foreground">{riskPreset ?? "--"}</dd>
        </div>
        <div>
          <dt className="text-muted">Exchanges monitoradas</dt>
          <dd className="mt-1 flex flex-wrap gap-1">
            {exchanges.length > 0 ? (
              exchanges.map((code) => (
                <Badge key={code} variant="outline">
                  {EXCHANGE_LABELS[code as keyof typeof EXCHANGE_LABELS] ?? code}
                </Badge>
              ))
            ) : (
              <span className="text-foreground">Nenhuma</span>
            )}
          </dd>
        </div>
      </dl>
    </section>
  );
}
