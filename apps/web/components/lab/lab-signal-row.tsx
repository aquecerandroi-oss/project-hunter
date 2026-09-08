"use client";

import { LabAsOf } from "@/components/lab/lab-as-of";
import { LabMarketLink } from "@/components/lab/lab-market-link";
import { LabResearchCells } from "@/components/lab/lab-research-cells";
import { reasonLabel } from "@/components/lab/lab-format";
import { MONEY_TOOLTIP, moneyForRow, priceAndTime, saidaText, usdtToBrl, type MoneyRuler } from "@/components/lab/lab-money";
import { ResultBadge } from "@/components/lab/lab-result-badge";
import type { SignalListItemOut } from "@/lib/api/lab-types";
import { formatBrlSigned, formatPct, formatUsdtSigned } from "@/lib/format";
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
 * tracking/touch state, `LabResearchCells`) render only when `showResearch`
 * is on, behind the "Detalhes de pesquisa" toggle in `LabSignalsTable`.
 */
export function LabSignalRow({ id, orgSlug, row, versionLabel, ruler, showResearch, rowHeight, selected, ariaRowIndex, onOpen }: LabSignalRowProps) {
  const { pnlUsdt, notionalUsdt, pctMove } = moneyForRow(row, ruler);
  const pnlBrl = pnlUsdt.value !== null ? usdtToBrl(pnlUsdt.value, ruler) : null;
  const pctColor = pctMove === null ? "text-fg-muted" : pctMove >= 0 ? "text-green" : "text-red";

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
      <td role="gridcell" className="px-3">
        <LabMarketLink orgSlug={orgSlug} symbol={row.market} />
      </td>
      <td role="gridcell" className="px-3 text-xs">
        <LabAsOf iso={row.decision_at} />
      </td>
      <td role="gridcell" title={MONEY_TOOLTIP} className="whitespace-nowrap px-3 text-right font-mono text-xs tabular-nums text-fg">
        {priceAndTime(row.virtual_entry, row.entry_ts)}
      </td>
      <td role="gridcell" title={MONEY_TOOLTIP} className="whitespace-nowrap px-3 text-right font-mono text-xs tabular-nums text-fg">
        {saidaText(row)}
      </td>
      <td role="gridcell" title={MONEY_TOOLTIP} className={cn("whitespace-nowrap px-3 text-right font-mono text-xs tabular-nums", pctColor)}>
        {pctMove !== null ? formatPct(pctMove) : "--"}
      </td>
      <td role="gridcell" title={MONEY_TOOLTIP} className="whitespace-nowrap px-3 text-right font-mono text-xs tabular-nums text-fg">
        {notionalUsdt.value !== null ? formatUsdtSigned(notionalUsdt.value) : <span className="text-fg-muted">{reasonLabel(notionalUsdt.reason ?? "")}</span>}
      </td>
      <td role="gridcell" title={MONEY_TOOLTIP} className="whitespace-nowrap px-3 text-right text-xs">
        <span className="mr-1.5 inline-block">
          <ResultBadge pnlUsdt={pnlUsdt.value} />
        </span>
        {pnlUsdt.value !== null ? (
          <span className="font-mono tabular-nums text-fg">
            {formatUsdtSigned(pnlUsdt.value)}
            {pnlBrl !== null && <span className="text-fg-muted"> ({formatBrlSigned(pnlBrl)})</span>}
          </span>
        ) : (
          <span className="text-fg-muted">{reasonLabel(pnlUsdt.reason ?? "sem motivo informado")}</span>
        )}
      </td>

      {showResearch && <LabResearchCells row={row} versionLabel={versionLabel} />}
    </tr>
  );
}
