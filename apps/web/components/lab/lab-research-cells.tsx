import { formatPrice } from "@/components/markets/format";
import { formatR, signColorClass } from "@/components/lab/lab-format";
import { TrackingStateChip } from "@/components/lab/lab-signal-chips";
import type { SignalListItemOut } from "@/lib/api/lab-types";
import { cn } from "@/lib/utils";

export const RESEARCH_SECONDARY_CELL = "hidden whitespace-nowrap px-3 text-right font-mono tabular-nums text-fg-muted lg:table-cell";

/**
 * The "Detalhes de pesquisa" columns of `LabSignalRow` (brief T3.17: "'R'
 * aparece só no toggle de pesquisa"; brief T3.17b item 5 narrows the list to
 * R líquido/R ex-funding/stop/alvo/tracking -- `Versão` moved into the
 * always-visible "Estratégia" cell, and `Referência`/`Toque` stay in the
 * per-signal detail panel instead of repeating in every row) -- split out so
 * the row's own JSX stays under the lint config's cyclomatic-complexity
 * budget and the money columns read as the row's real subject.
 */
export function LabResearchCells({ row }: { row: SignalListItemOut }) {
  const r = formatR(row.r_multiple, row.r_multiple_reason);
  const rExFunding = row.r_ex_funding;

  return (
    <>
      <td role="gridcell" className={cn("whitespace-nowrap px-3 text-right font-mono text-xs tabular-nums", r.isValue ? signColorClass(row.r_multiple) : "text-fg-muted")}>
        {r.text}
      </td>
      <td role="gridcell" className={cn(RESEARCH_SECONDARY_CELL, rExFunding !== null && signColorClass(rExFunding))}>
        {rExFunding !== null ? `${rExFunding}R` : "--"}
      </td>
      <td role="gridcell" className={RESEARCH_SECONDARY_CELL}>{formatPrice(row.stop)}</td>
      <td role="gridcell" className={RESEARCH_SECONDARY_CELL}>{formatPrice(row.target1)}</td>
      <td role="gridcell" className="whitespace-nowrap px-3">
        <TrackingStateChip state={row.tracking_state} reason={row.no_entry_reason ?? row.censored_reason} />
      </td>
    </>
  );
}
