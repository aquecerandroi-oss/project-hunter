import { Badge } from "@/components/ui/badge";

// `strategy_versions.purpose` (`packages/core/.../db/models/agents.py`'s
// CHECK constraint): "research_only" | "paper" | "live" -- the Shadow Lab
// never carries "live" (SHADOW-LAB.md), but the map stays total so an
// unexpected value still renders its own raw code instead of disappearing.
const PURPOSE_LABEL: Record<string, string> = {
  research_only: "pesquisa",
  paper: "paper",
  live: "live",
};

export function purposeLabel(purpose: string): string {
  return PURPOSE_LABEL[purpose] ?? purpose;
}

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
      <Badge variant={purpose === "paper" ? "info" : "outline"} className="px-1.5 py-0 text-[10px]">
        {purposeLabel(purpose)}
      </Badge>
    </div>
  );
}
