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

export interface LabVersionChip {
  versionId: string;
  /** `versionLabelById`'s own merged shape, `"<strategy_key>/<version>"`. */
  label: string;
  purpose: string;
}

/** `versionLabelById`'s merged shape is always `"<strategy_key>/<version>"` (`lab-page-body.tsx`) -- split back apart so the strategy key can render once and each chip can show only its own version. */
function splitVersionLabel(label: string): { key: string; version: string } {
  const slash = label.indexOf("/");
  return slash === -1 ? { key: label, version: label } : { key: label.slice(0, slash), version: label.slice(slash + 1) };
}

/**
 * The "Estratégia" cell for a group of sibling-version signals that decided
 * the exact same operation (brief T3.38, Everton's screenshot: three
 * identical `RAYSOLUSDT` rows -- `momentum/v2 pesquisa`, `momentum/v3
 * paper`, `momentum/v4 pesquisa` -- collapsed into one). The strategy key
 * renders once (every member shares it); one chip per version follows,
 * `<version>` or `<version> paper` when that member's own purpose is the
 * wallet-spending cohort, same badge colour `LabStrategyCell` already uses
 * for a single row.
 */
export function LabStrategyChips({ chips }: { chips: LabVersionChip[] }) {
  const first = chips[0];
  const key = first ? splitVersionLabel(first.label).key : "";
  return (
    <div className="flex flex-col items-start gap-1">
      <span className="font-mono text-xs text-fg">{key}</span>
      <div className="flex flex-wrap gap-1">
        {chips.map((chip) => {
          const { version } = splitVersionLabel(chip.label);
          const text = chip.purpose === "paper" ? `${version} paper` : version;
          return (
            <Badge key={chip.versionId} variant={chip.purpose === "paper" ? "info" : "outline"} className="px-1.5 py-0 text-[11px]">
              {text}
            </Badge>
          );
        })}
      </div>
    </div>
  );
}
