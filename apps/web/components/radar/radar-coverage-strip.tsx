import { ANOMALY_TYPE_LABEL } from "@/components/radar/labels";
import {
  buildHeadline,
  buildReopenConditions,
  classifyDetector,
  DETECTOR_STATE_LABEL,
  disarmReasonLabel,
} from "@/components/radar/radar-coverage-format";
import { Badge } from "@/components/ui/badge";
import type { badgeVariants } from "@/components/ui/badge";
import type { VariantProps } from "class-variance-authority";
import type { RadarCoverageOut } from "@/lib/api/radar-coverage-types";
import { cn } from "@/lib/utils";

type BadgeVariant = VariantProps<typeof badgeVariants>["variant"];

const DETECTOR_BADGE_VARIANT: Record<ReturnType<typeof classifyDetector>, BadgeVariant> = {
  producing: "positive",
  disarmed: "outline",
  silent: "negative",
};

/** Anchor target for the empty states' "veja o estado completo do Radar" link (`radar-empty.tsx`, `opportunities-empty.tsx`). */
export const RADAR_COVERAGE_STRIP_ID = "estado-do-radar";

/**
 * T3.46's "Estado do Radar" strip -- shared by `/radar` and `/opportunities`
 * (both Server Components; this reads only the `coverage` prop they already
 * fetched server-side, no client state, no polling). Every number traces
 * back to `GET /api/v1/radar/coverage`; a missing field always renders an
 * honest fallback clause, never a fabricated zero
 * (`radar-coverage-format.ts`).
 */
export function RadarCoverageStrip({ coverage }: { coverage: RadarCoverageOut | null }) {
  if (!coverage) {
    return (
      <section
        id={RADAR_COVERAGE_STRIP_ID}
        className="rounded-lg border border-dashed border-border bg-bg-elevated p-4 text-sm text-fg-muted"
      >
        Não foi possível ler o estado do Radar agora. As oportunidades abaixo continuam sendo as que o Radar realmente pontuou.
      </section>
    );
  }

  const reopenConditions = buildReopenConditions(coverage);

  return (
    <section id={RADAR_COVERAGE_STRIP_ID} className="flex flex-col gap-4 rounded-lg border border-border bg-bg-elevated p-4">
      <p className="text-sm text-fg">{buildHeadline(coverage)}</p>

      <div>
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-fg-muted">Detectores (últimos 31 dias)</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="text-xs text-fg-muted">
                <th className="pb-1 pr-4 font-medium">Detector</th>
                <th className="pb-1 pr-4 font-medium">Estado</th>
                <th className="pb-1 font-medium">Detalhe</th>
              </tr>
            </thead>
            <tbody>
              {coverage.detectors.map((detector) => {
                const state = classifyDetector(detector);
                return (
                  <tr key={detector.type} className="border-t border-border/60">
                    <td className="py-1.5 pr-4 text-fg">{ANOMALY_TYPE_LABEL[detector.type]}</td>
                    <td className="py-1.5 pr-4">
                      <Badge variant={DETECTOR_BADGE_VARIANT[state]}>{DETECTOR_STATE_LABEL[state]}</Badge>
                    </td>
                    <td className="py-1.5 font-mono text-xs tabular-nums text-fg-muted">
                      {state === "producing" &&
                        `${detector.rows_31d} ${detector.rows_31d === 1 ? "anomalia" : "anomalias"}`}
                      {state === "disarmed" && detector.disarmed_reason && disarmReasonLabel(detector.disarmed_reason)}
                      {state === "silent" &&
                        "produziu zero linhas e o scanner não declarou motivo -- defeito conhecido, não filtro intencional"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div>
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-fg-muted">Quando o estudo reabre</h2>
        <p className="mb-2 text-xs text-fg-muted">As três condições abaixo precisam valer ao mesmo tempo.</p>
        <div className="flex flex-col gap-3">
          {reopenConditions.map((condition) => (
            <div key={condition.id} className="flex flex-col gap-1">
              <div className="flex items-center justify-between text-xs">
                <span className="text-fg">{condition.label}</span>
                <span className={cn("font-mono tabular-nums", condition.met ? "text-green" : "text-fg-muted")}>
                  {condition.currentText}
                </span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-bg-overlay" role="presentation">
                <div
                  className={cn("h-1.5 rounded-full", condition.met ? "bg-green" : "bg-info")}
                  style={{ width: `${condition.pct}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
