import { Badge } from "@/components/ui/badge";
import type { SystemInfo } from "@/lib/api/types";

export interface FeatureFlagsTableProps {
  features: SystemInfo["features"];
}

const FLAG_LABELS: Record<keyof SystemInfo["features"], string> = {
  enable_live_trading: "Live trading",
  enable_social_intelligence: "Social intelligence",
  enable_onchain: "On-chain",
  enable_stripe: "Stripe",
  enable_llm_analysis: "Análise via LLM",
  enable_arena: "Agent Arena",
  enable_backtests: "Backtests",
};

/** `ENABLE_*` system feature flags (docs/PRODUCT.md §5) -- read directly off `/api/v1/system/info`. */
export function FeatureFlagsTable({ features }: FeatureFlagsTableProps) {
  const entries = Object.entries(features) as [keyof SystemInfo["features"], boolean][];

  return (
    <section className="rounded-lg border border-border bg-bg-elevated p-4">
      <h2 className="text-xs font-medium uppercase tracking-wide text-fg-muted">Feature flags</h2>
      <table className="mt-3 w-full text-left text-[13px]">
        <tbody>
          {entries.map(([key, enabled]) => (
            <tr key={key} className="h-8 border-t border-border first:border-t-0">
              <td className="text-fg">{FLAG_LABELS[key]}</td>
              <td className="text-right">
                <Badge variant={enabled ? "positive" : "outline"}>{enabled ? "Ativa" : "Desativada"}</Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
