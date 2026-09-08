"use client";

import { LabExitCell } from "@/components/lab/lab-exit-cell";
import { labCellVisibilityClass } from "@/components/lab/lab-signals-table-head";
import { LabMarketLink } from "@/components/lab/lab-market-link";
import { LabMoneyOrReason, LabMoneyRangeValue, LabResultValue } from "@/components/lab/lab-money-cells";
import { LabPriceTimeCell } from "@/components/lab/lab-price-time-cell";
import { LabResearchCells } from "@/components/lab/lab-research-cells";
import { notionalRangeUsdt, pnlRangeUsdt, type MoneyRange } from "@/components/lab/lab-signal-divergence";
import { LabStrategyCell, LabStrategyChips, type LabVersionChip } from "@/components/lab/lab-strategy-cell";
import { WhenCell } from "@/components/lab/lab-when-cell";
import { durationText, pctColorClass } from "@/components/lab/lab-format";
import { moneyForRow, usdtToBrl, type MoneyOrReason, type MoneyRuler } from "@/components/lab/lab-money";
import { ResultBadge } from "@/components/lab/lab-result-badge";
import type { SignalListItemOut } from "@/lib/api/lab-types";
import { formatPct } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Finding 2 of the T3.38 review: a merged group whose members still disagree
 * on money (should now be impossible once T3.38c-api's `stop` fix is live)
 * needs the real range instead of `row`'s (the group's primary) own value
 * standing in for the whole group. Split out of `LabSignalRow` itself so
 * that function's own cyclomatic complexity stays under the lint config's
 * budget.
 */
function moneyRangesForRow(members: SignalListItemOut[] | undefined, ruler: MoneyRuler): { pnlRange: MoneyRange | null; notionalRange: MoneyRange | null } {
  if (!members || members.length <= 1) return { pnlRange: null, notionalRange: null };
  return { pnlRange: pnlRangeUsdt(members, ruler), notionalRange: notionalRangeUsdt(members, ruler) };
}

/** "Resultado" cell content -- the range when the group's members diverge, else the ordinary badge + value. Its own component (rather than inline JSX) for the same complexity-budget reason. */
function ResultCell({ pnlRange, pnlUsdt, pnlBrl }: { pnlRange: MoneyRange | null; pnlUsdt: MoneyOrReason; pnlBrl: number | null }) {
  if (pnlRange) return <LabMoneyRangeValue range={pnlRange} />;
  return (
    <>
      <span className="mr-1.5 inline-block">
        <ResultBadge pnlUsdt={pnlUsdt.value} />
      </span>
      <LabResultValue pnlUsdt={pnlUsdt} pnlBrl={pnlBrl} />
    </>
  );
}

export interface LabSignalRowProps {
  id: string;
  orgSlug: string;
  row: SignalListItemOut;
  versionLabel: string;
  ruler: MoneyRuler;
  showResearch: boolean;
  rowHeight: number;
  selected: boolean;
  ariaRowIndex: number;
  /** `true` when the side panel is open (`lg`) -- "Duração"/"Quantia simulada" hide until `xl` (brief T3.24b item [3]), same rule the header applies. */
  panelOpen: boolean;
  onOpen: () => void;
  /**
   * Present (length > 1) when this row merges more than one sibling-version
   * signal that decided the exact same operation (brief T3.38) -- the
   * "Estratégia" cell then renders `LabStrategyChips` instead of the single
   * `LabStrategyCell`. `row`'s own fields (market/prices/result) still come
   * from the group's `primary` -- every member shares them by definition.
   */
  versionChips?: LabVersionChip[] | undefined;
  /**
   * Every signal behind this row's group (finding 2 of the T3.38 review) --
   * length <= 1 outside a merged row. Used only to detect (and, when it
   * happens, render as a range instead of a single figure) money divergence
   * between siblings; the row's own displayed values still come from `row`
   * (the group's `primary`) whenever every member actually agrees.
   */
  members?: SignalListItemOut[] | undefined;
}

/**
 * One row of the Shadow Lab signals table -- money columns first, always
 * visible (brief T3.17: what a signal entered with, what it left with,
 * profit or loss, in plain USDT/BRL); research columns (R, raw levels,
 * tracking state, `LabResearchCells`) render only when `showResearch` is on,
 * behind the "Detalhes de pesquisa" toggle in `LabSignalsTable`.
 *
 * Brief T3.17b (Everton's own screenshot) added `Estratégia` and `Duração`
 * to the always-visible set and rewrote `Entrou`/`Saiu` as two-line,
 * fixed-width cells that never wrap or truncate mid-word.
 */
export function LabSignalRow({
  id,
  orgSlug,
  row,
  versionLabel,
  ruler,
  showResearch,
  rowHeight,
  selected,
  ariaRowIndex,
  panelOpen,
  onOpen,
  versionChips,
  members,
}: LabSignalRowProps) {
  const { pnlUsdt, notionalUsdt, pctMove } = moneyForRow(row, ruler);
  const pnlBrl = pnlUsdt.value !== null ? usdtToBrl(pnlUsdt.value, ruler) : null;
  const { pnlRange, notionalRange } = moneyRangesForRow(members, ruler);
  const duration = durationText(row.entry_ts, row.exit_ts);
  const mobileHidden = labCellVisibilityClass({ mobileHidden: true }, panelOpen);
  const panelHidden = labCellVisibilityClass({ panelHidden: true }, panelOpen);

  return (
    <tr
      id={id}
      role="row"
      aria-rowindex={ariaRowIndex}
      aria-selected={selected}
      style={{ height: rowHeight }}
      className={cn("cursor-pointer border-t border-border hover:bg-bg-overlay", selected && "bg-bg-overlay ring-1 ring-inset ring-gold")}
      onClick={onOpen}
    >
      <td role="gridcell" className="whitespace-nowrap px-3">
        {versionChips && versionChips.length > 1 ? (
          <LabStrategyChips chips={versionChips} />
        ) : (
          <LabStrategyCell versionLabel={versionLabel} purpose={row.purpose} />
        )}
      </td>
      <td role="gridcell" className="px-3">
        <LabMarketLink orgSlug={orgSlug} symbol={row.market} />
      </td>
      <td role="gridcell" className={cn("whitespace-nowrap px-3 text-xs", mobileHidden)}>
        <WhenCell iso={row.decision_at} />
      </td>
      <td role="gridcell" className={cn("whitespace-nowrap px-3 text-right text-xs", mobileHidden)}>
        <LabPriceTimeCell price={row.virtual_entry} ts={row.entry_ts} />
      </td>
      <td role="gridcell" className={cn("px-3 text-right text-xs", mobileHidden)}>
        <LabExitCell row={row} />
      </td>
      <td
        role="gridcell"
        title={duration.reason ?? undefined}
        className={cn("whitespace-nowrap px-3 text-right font-mono text-xs tabular-nums text-fg-muted", panelHidden)}
      >
        {duration.text}
      </td>
      <td role="gridcell" className={cn("whitespace-nowrap px-3 text-right font-mono text-xs tabular-nums", mobileHidden, pctColorClass(pctMove))}>
        {pctMove !== null ? formatPct(pctMove) : "--"}
      </td>
      <td role="gridcell" className={cn("whitespace-nowrap px-3 text-right font-mono text-xs tabular-nums text-fg", panelHidden)}>
        {notionalRange ? <LabMoneyRangeValue range={notionalRange} /> : <LabMoneyOrReason money={notionalUsdt} />}
      </td>
      <td role="gridcell" className="min-w-[150px] whitespace-nowrap px-3 text-right text-xs">
        <ResultCell pnlRange={pnlRange} pnlUsdt={pnlUsdt} pnlBrl={pnlBrl} />
      </td>

      {showResearch && <LabResearchCells row={row} />}
    </tr>
  );
}
