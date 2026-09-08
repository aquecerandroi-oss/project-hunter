import { Badge } from "@/components/ui/badge";
import { purposeLabel } from "@/components/lab/labels";

/**
 * "Estratégia" column (brief T3.17b item 5): key/version (already merged as
 * `"momentum/v2"` by the page's `versionLabelById`) plus a purpose chip --
 * moved out of the research-only toggle since which strategy emitted a
 * signal is a fact every reader needs, not a research detail.
 */
export function LabStrategyCell({ versionLabel, purpose }: { versionLabel: string; purpose: string }) {
  return (
    <div className="flex flex-col items-start gap-1">
      <span className="font-mono text-xs text-fg">{versionLabel}</span>
      <Badge variant={purpose === "paper" ? "info" : "outline"} className="px-1.5 py-0 text-[11px]">
        {purposeLabel(purpose)}
      </Badge>
    </div>
  );
}
