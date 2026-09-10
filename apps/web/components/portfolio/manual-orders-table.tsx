import { Badge } from "@/components/ui/badge";
import { TableShell } from "@/components/portfolio/portfolio-activity-tables";
import { DIRECTION_LABEL } from "@/components/portfolio/labels";
import { BrasiliaInstant } from "@/components/time/brasilia-instant";
import type { ManualOrderListItem } from "@/lib/api/manual-orders-types";
import { formatUsdt } from "@/lib/format";

export interface ManualOrdersTableProps {
  items: ManualOrderListItem[];
  asOf: string;
}

const STATUS_LABEL: Record<string, string> = {
  pending: "Pendente",
  decided: "Decidida",
};

/** `market_id` is the only market identity `ManualOrderOut` carries (T3.68) -- no exchange/symbol join happens on this list, so this shows the id itself rather than fabricating a friendly label this endpoint never sent. */
function marketLabel(item: ManualOrderListItem): string {
  return `${item.market_id.slice(0, 8)}…`;
}

function decisionBadge(item: ManualOrderListItem): { variant: "default" | "positive" | "negative"; label: string } {
  if (item.status === "pending" || !item.decision) return { variant: "default", label: "Pendente" };
  return item.decision.approved ? { variant: "positive", label: "Aprovada" } : { variant: "negative", label: "Recusada" };
}

/** `Sizing.notional` once approved -- the size the engine actually granted, never the operator's own requested cap (`ManualOrderOut` carries no `requested_notional`; that input is not echoed back by this endpoint, T3.68). `null` for anything pending/refused/without sizing. */
function approvedSize(item: ManualOrderListItem): string | null {
  if (!item.decision?.approved || !item.decision.sizing) return null;
  return formatUsdt(item.decision.sizing.notional);
}

/**
 * "Propostas" (T3.72 item 2): the manual paper request list, newest first --
 * replaces `PortfolioProposalsEmpty` once at least one request exists. Same
 * table shell as `portfolio-activity-tables.tsx` for visual consistency
 * across the Carteira screen. Columns mirror `ManualOrderOut` exactly
 * (`market_id`/`direction`/`status`/`decision`/`filed_at`, T3.68/T3.72c) --
 * no `stop`/`requested_notional` column, because this endpoint never echoes
 * the operator's own request inputs back on the list.
 */
export function ManualOrdersTable({ items, asOf }: ManualOrdersTableProps) {
  return (
    <TableShell title="Propostas (ordens manuais)" emptyNote="Nenhuma ordem manual enviada ainda." asOf={asOf} count={items.length}>
      <table className="w-full text-left text-[13px]">
        <thead>
          <tr className="text-xs text-fg-muted">
            <th className="py-1 pr-3">Mercado</th>
            <th className="py-1 pr-3">Direção</th>
            <th className="py-1 pr-3">Status</th>
            <th className="py-1 pr-3">Decisão</th>
            <th className="py-1 pr-3">Tamanho aprovado</th>
            <th className="py-1 pr-3">Enviada em (Brasília)</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const badge = decisionBadge(item);
            const size = approvedSize(item);
            return (
              <tr key={item.request_id} className="border-t border-border">
                <td className="py-1 pr-3 font-mono" title={item.market_id}>
                  {marketLabel(item)}
                </td>
                <td className="py-1 pr-3">
                  <Badge variant={item.direction === "long" ? "positive" : "negative"}>{DIRECTION_LABEL[item.direction]}</Badge>
                </td>
                <td className="py-1 pr-3">{STATUS_LABEL[item.status] ?? item.status}</td>
                <td className="py-1 pr-3">
                  <Badge variant={badge.variant}>{badge.label}</Badge>
                </td>
                <td className="py-1 pr-3 font-mono tabular-nums">{size ?? "--"}</td>
                <td className="py-1 pr-3">
                  <BrasiliaInstant iso={item.filed_at} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </TableShell>
  );
}
