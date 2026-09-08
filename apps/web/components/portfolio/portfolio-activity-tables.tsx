import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { signColorClass } from "@/components/portfolio/portfolio-format";
import { BrasiliaInstant } from "@/components/time/brasilia-instant";
import type { OrderRow, PortfolioTradeRow, PositionRow } from "@/lib/api/portfolio-types";
import { formatPct, formatUsdt } from "@/lib/format";

/**
 * Positions/orders/trades (brief item 6): honestly empty today, `as_of`
 * always shown. `routers/portfolio.py`'s own summaries say it plainly ("empty
 * until T3.4/T3.5 land a writer") -- this is the *ausência operacional* case
 * (docs/DESIGN.md §2): the read is real, the table is implemented, there is
 * simply nothing written yet, unlike `PortfolioProposalsEmpty`'s "não
 * construído ainda". Not virtualized: `CLAUDE.md` requires virtualization at
 * >= 200 rows, and there is no writer to ever produce that many yet -- adding
 * it now would be speculative machinery for a table that is empty by
 * contract (revisit once T3.4/T3.5 land).
 */

function AsOfNote({ asOf, count }: { asOf: string; count: number }) {
  return (
    <p className="text-xs text-fg-subtle">
      {count} {count === 1 ? "linha" : "linhas"} · consultado em <BrasiliaInstant iso={asOf} />
    </p>
  );
}

function TableShell({ title, emptyNote, asOf, count, children }: { title: string; emptyNote: string; asOf: string; count: number; children: ReactNode }) {
  return (
    <div className="rounded-md border border-border p-4">
      <h3 className="text-sm font-semibold text-fg">{title}</h3>
      {count === 0 ? (
        <p className="mt-2 text-sm text-fg-muted">{emptyNote}</p>
      ) : (
        <div className="mt-2 overflow-x-auto">{children}</div>
      )}
      <div className="mt-2">
        <AsOfNote asOf={asOf} count={count} />
      </div>
    </div>
  );
}

export interface PositionsTableProps {
  items: PositionRow[];
  asOf: string;
}

export function PositionsTable({ items, asOf }: PositionsTableProps) {
  return (
    <TableShell title="Posições" emptyNote="Nenhuma posição aberta ainda." asOf={asOf} count={items.length}>
      <table className="w-full text-left text-[13px]">
        <thead>
          <tr className="text-xs text-fg-muted">
            <th className="py-1 pr-3">Direção</th>
            <th className="py-1 pr-3">Qtd</th>
            <th className="py-1 pr-3">Entrada média</th>
            <th className="py-1 pr-3">Mark</th>
            <th className="py-1 pr-3">Stop</th>
            <th className="py-1 pr-3">PnL não realizado</th>
            <th className="py-1 pr-3">Status</th>
            <th className="py-1 pr-3">Aberta em (Brasília)</th>
          </tr>
        </thead>
        <tbody>
          {items.map((p) => (
            <tr key={p.id} className="border-t border-border">
              <td className="py-1 pr-3">
                <Badge variant={p.direction === "long" ? "positive" : p.direction === "short" ? "negative" : "default"}>{p.direction}</Badge>
              </td>
              <td className="py-1 pr-3 font-mono tabular-nums">{p.qty}</td>
              <td className="py-1 pr-3 font-mono tabular-nums">{formatUsdt(p.avg_entry_price)}</td>
              <td className="py-1 pr-3 font-mono tabular-nums">{p.mark_price !== null ? formatUsdt(p.mark_price) : "indisponível"}</td>
              <td className="py-1 pr-3 font-mono tabular-nums">{p.stop_price !== null ? formatUsdt(p.stop_price) : "sem stop"}</td>
              <td className={`py-1 pr-3 font-mono tabular-nums ${signColorClass(p.unrealized_pnl)}`}>{formatUsdt(p.unrealized_pnl)}</td>
              <td className="py-1 pr-3">{p.status}</td>
              <td className="py-1 pr-3">
                <BrasiliaInstant iso={p.opened_at} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableShell>
  );
}

export interface OrdersTableProps {
  items: OrderRow[];
  asOf: string;
}

export function OrdersTable({ items, asOf }: OrdersTableProps) {
  return (
    <TableShell title="Ordens" emptyNote="Nenhuma ordem registrada ainda." asOf={asOf} count={items.length}>
      <table className="w-full text-left text-[13px]">
        <thead>
          <tr className="text-xs text-fg-muted">
            <th className="py-1 pr-3">Lado</th>
            <th className="py-1 pr-3">Tipo</th>
            <th className="py-1 pr-3">Propósito</th>
            <th className="py-1 pr-3">Modo</th>
            <th className="py-1 pr-3">Status</th>
            <th className="py-1 pr-3">Qtd</th>
            <th className="py-1 pr-3">Preço</th>
            <th className="py-1 pr-3">Preenchida</th>
            <th className="py-1 pr-3">Criada em (Brasília)</th>
          </tr>
        </thead>
        <tbody>
          {items.map((o) => (
            <tr key={o.id} className="border-t border-border">
              <td className="py-1 pr-3">
                <Badge variant={o.side === "buy" ? "positive" : "negative"}>{o.side}</Badge>
              </td>
              <td className="py-1 pr-3">{o.type}</td>
              <td className="py-1 pr-3">{o.purpose}</td>
              <td className="py-1 pr-3">{o.execution_mode}</td>
              <td className="py-1 pr-3">{o.status}</td>
              <td className="py-1 pr-3 font-mono tabular-nums">{o.qty}</td>
              <td className="py-1 pr-3 font-mono tabular-nums">{o.price !== null ? formatUsdt(o.price) : "a mercado"}</td>
              <td className="py-1 pr-3 font-mono tabular-nums">{o.filled_qty}</td>
              <td className="py-1 pr-3">
                <BrasiliaInstant iso={o.created_at} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableShell>
  );
}

export interface TradesTableProps {
  items: PortfolioTradeRow[];
  asOf: string;
}

export function TradesTable({ items, asOf }: TradesTableProps) {
  return (
    <TableShell title="Trades" emptyNote="Nenhum trade fechado ainda." asOf={asOf} count={items.length}>
      <table className="w-full text-left text-[13px]">
        <thead>
          <tr className="text-xs text-fg-muted">
            <th className="py-1 pr-3">Direção</th>
            <th className="py-1 pr-3">Entrada</th>
            <th className="py-1 pr-3">Saída</th>
            <th className="py-1 pr-3">Qtd</th>
            <th className="py-1 pr-3">Taxas</th>
            <th className="py-1 pr-3">PnL</th>
            <th className="py-1 pr-3">PnL %</th>
            <th className="py-1 pr-3">Motivo de saída</th>
            <th className="py-1 pr-3">Fechado em (Brasília)</th>
          </tr>
        </thead>
        <tbody>
          {items.map((t) => (
            <tr key={t.id} className="border-t border-border">
              <td className="py-1 pr-3">
                <Badge variant={t.direction === "long" ? "positive" : t.direction === "short" ? "negative" : "default"}>{t.direction}</Badge>
              </td>
              <td className="py-1 pr-3 font-mono tabular-nums">{formatUsdt(t.entry_price)}</td>
              <td className="py-1 pr-3 font-mono tabular-nums">{formatUsdt(t.exit_price)}</td>
              <td className="py-1 pr-3 font-mono tabular-nums">{t.qty}</td>
              <td className="py-1 pr-3 font-mono tabular-nums">{formatUsdt(t.fees)}</td>
              <td className={`py-1 pr-3 font-mono tabular-nums ${signColorClass(t.pnl)}`}>{formatUsdt(t.pnl)}</td>
              <td className="py-1 pr-3 font-mono tabular-nums">{t.pnl_pct !== null ? formatPct(t.pnl_pct) : "indisponível"}</td>
              <td className="py-1 pr-3">{t.exit_reason ?? "--"}</td>
              <td className="py-1 pr-3">
                <BrasiliaInstant iso={t.closed_at} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableShell>
  );
}
