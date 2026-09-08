import { formatPrice } from "@/components/markets/format";
import { EXIT_REASON_LABEL, reasonLabel } from "@/components/lab/lab-format";
import { WhenCell } from "@/components/lab/lab-when-cell";
import type { SignalListItemOut } from "@/lib/api/lab-types";

/**
 * The Everton screenshot's own list (brief T3.17b, "What Everton saw" item
 * 5): the "Saiu" column must say WHY a signal left, not just when -- alvo,
 * stop, expirou, invalidada, censurada + motivo, or aberta -- never truncated
 * mid-word ("motivo: s…"). Price+time stay two lines max (`LabPriceTimeCell`'s
 * own rule); the motivo joins the time line for a real exit, since a
 * non-exited row (aberta/não entrou/censurada) has no price line to spare a
 * third line for.
 */
export function LabExitCell({ row }: { row: SignalListItemOut }) {
  if (row.exit_price !== null) {
    return (
      <span className="flex flex-col items-end leading-tight">
        <span className="font-mono tabular-nums text-fg">{formatPrice(row.exit_price)}</span>
        <span className="flex items-center gap-1 whitespace-nowrap text-[11px] text-fg-muted">
          <WhenCell iso={row.exit_ts} suffix={false} className="font-mono tabular-nums" />
          <span>· {EXIT_REASON_LABEL[row.result]}</span>
        </span>
      </span>
    );
  }

  if (row.tracking_state === "no_entry") {
    const reason = reasonLabel(row.no_entry_reason ?? "sem motivo informado");
    const full = `não entrou: ${reason}`;
    return (
      <span className="block max-w-[220px] truncate text-fg-muted" title={full}>
        {full}
      </span>
    );
  }

  if (row.tracking_state === "censored") {
    const reason = reasonLabel(row.censored_reason ?? "sem motivo informado");
    const full = `censurada: ${reason}`;
    return (
      <span className="block max-w-[220px] truncate text-fg-muted" title={full}>
        {full}
      </span>
    );
  }

  return <span className="text-fg-muted">aberta</span>;
}
