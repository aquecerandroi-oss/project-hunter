import { maturityBarText, maturityRatios } from "@/components/lab/lab-scoreboard";
import type { ScoreboardMaturityOut } from "@/lib/api/lab-types";

/**
 * The Placar card's maturity bar (brief T3.18 item 3, Everton's own example:
 * "37 de 100 resultados · 2 de 30 dias"). Two independent tracks (outcomes,
 * distinct days) since both thresholds must clear together (SHADOW-LAB.md
 * §9/§10) -- a single averaged bar would hide which one is still short.
 * `--color-info` (docs/DESIGN.md §1: "informação neutra") on purpose, not
 * gold: this is progress information, not the page's one primary action.
 */
export function LabMaturityBar({ maturity }: { maturity: ScoreboardMaturityOut }) {
  const { outcomesPct, daysPct } = maturityRatios(maturity);
  return (
    <div className="flex min-w-[160px] flex-col gap-1">
      <div className="flex gap-1" role="presentation">
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-bg-overlay" title="resultados avaliáveis / limiar">
          <div className="h-1.5 rounded-full bg-info" style={{ width: `${outcomesPct}%` }} />
        </div>
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-bg-overlay" title="dias distintos / limiar">
          <div className="h-1.5 rounded-full bg-info" style={{ width: `${daysPct}%` }} />
        </div>
      </div>
      <span className="font-mono text-[11px] tabular-nums text-fg-subtle">{maturityBarText(maturity)}</span>
    </div>
  );
}
