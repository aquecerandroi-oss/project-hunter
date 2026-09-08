"use client";

import { LabExitCell } from "@/components/lab/lab-exit-cell";
import { LabMarketLink } from "@/components/lab/lab-market-link";
import { LabMoneyOrReason, LabResultValue } from "@/components/lab/lab-money-cells";
import { LabPriceTimeCell } from "@/components/lab/lab-price-time-cell";
import { LabResearchCells } from "@/components/lab/lab-research-cells";
import { LabStrategyCell } from "@/components/lab/lab-strategy-cell";
import { WhenCell } from "@/components/lab/lab-when-cell";
import { durationText, pctColorClass } from "@/components/lab/lab-format";
import { MONEY_TOOLTIP, moneyForRow, usdtToBrl, type MoneyRuler } from "@/components/lab/lab-money";
import { ResultBadge } from "@/components/lab/lab-result-badge";
import type { SignalListItemOut } from "@/lib/api/lab-types";
import { formatPct } from "@/lib/format";
import { cn } from "@/lib/utils";

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
  onOpen: () => void;
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
export function LabSignalRow({ id, orgSlug, row, versionLabel, ruler, showResearch, rowHeight, selected, ariaRowIndex, onOpen }: LabSignalRowProps) {
  const { pnlUsdt, notionalUsdt, pctMove } = moneyForRow(row, ruler);
  const pnlBrl = pnlUsdt.value !== null ? usdtToBrl(pnlUsdt.value, ruler) : null;
  const duration = durationText(row.entry_ts, row.exit_ts);

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
        <LabStrategyCell versionLabel={versionLabel} purpose={row.purpose} />
      </td>
      <td role="gridcell" className="px-3">
        <LabMarketLink orgSlug={orgSlug} symbol={row.market} />
      </td>
      <td role="gridcell" className="whitespace-nowrap px-3 text-xs">
        <WhenCell iso={row.decision_at} />
      </td>
      <td role="gridcell" title={MONEY_TOOLTIP} className="whitespace-nowrap px-3 text-right text-xs">
        <LabPriceTimeCell price={row.virtual_entry} ts={row.entry_ts} />
      </td>
      <td role="gridcell" title={MONEY_TOOLTIP} className="px-3 text-right text-xs">
        <LabExitCell row={row} />
      </td>
      <td
        role="gridcell"
        title={duration.reason ?? undefined}
        className="whitespace-nowrap px-3 text-right font-mono text-xs tabular-nums text-fg-muted"
      >
        {duration.text}
      </td>
      <td role="gridcell" title={MONEY_TOOLTIP} className={cn("whitespace-nowrap px-3 text-right font-mono text-xs tabular-nums", pctColorClass(pctMove))}>
        {pctMove !== null ? formatPct(pctMove) : "--"}
      </td>
      <td role="gridcell" title={MONEY_TOOLTIP} className="whitespace-nowrap px-3 text-right font-mono text-xs tabular-nums text-fg">
        <LabMoneyOrReason money={notionalUsdt} />
      </td>
      <td role="gridcell" title={MONEY_TOOLTIP} className="min-w-[150px] whitespace-nowrap px-3 text-right text-xs">
        <span className="mr-1.5 inline-block">
          <ResultBadge pnlUsdt={pnlUsdt.value} />
        </span>
        <LabResultValue pnlUsdt={pnlUsdt} pnlBrl={pnlBrl} />
      </td>

      {showResearch && <LabResearchCells row={row} />}
    </tr>
  );
}
