"use client";

import { Badge } from "@/components/ui/badge";
import { computeAgeMs, formatAge, useAgeTicker } from "@/hooks/useAgeTicker";
import type { WorkerHeartbeat, WorkerStatus } from "@/lib/api/types";

export interface WorkersTableProps {
  /** `/system/workers` -- a flat `hb:*` scan (`schemas/system.py`'s `WorkerHeartbeatOut`). `role === "market"` rows also carry `ws_state`/`markets_monitored`/etc; every other role has them `null`. */
  workers: WorkerHeartbeat[];
}

const STATUS_VARIANT: Record<WorkerStatus, "positive" | "warning" | "negative"> = {
  alive: "positive",
  late: "warning",
  dead: "negative",
};

function AgeCell({ ts }: { ts: string }) {
  const now = useAgeTicker();
  const ageMs = computeAgeMs(ts, now);
  return <>{ageMs !== null ? formatAge(ageMs) : "?"}</>;
}

/**
 * `/system/workers` (T1.4): real `hb:*` heartbeats, replacing the old
 * "nenhum processo registrado (M1)" placeholder (docs/plans/M1.md T1.5).
 * Ages tick live (`useAgeTicker`) so a page left open doesn't read as
 * healthy forever between `revalidate` cycles -- `status`/`ws_state`
 * themselves stay the server's last snapshot until the next fetch, which is
 * disclosed rather than hidden.
 */
export function WorkersTable({ workers }: WorkersTableProps) {
  const exchanges = workers.filter((worker) => worker.role === "market" && worker.ws_state !== null);

  return (
    <div className="flex flex-col gap-4">
      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full text-left text-[13px]">
          <thead className="bg-bg-overlay text-xs text-fg-muted">
            <tr>
              <th className="h-8 px-3 font-medium">Role</th>
              <th className="h-8 px-3 font-medium">Instância</th>
              <th className="h-8 px-3 font-medium">Status</th>
              <th className="h-8 px-3 font-medium text-right">Idade</th>
              <th className="h-8 px-3 font-medium text-right">Erros</th>
              <th className="h-8 px-3 font-medium">Versão</th>
            </tr>
          </thead>
          <tbody>
            {workers.length === 0 ? (
              <tr className="h-8 border-t border-border">
                <td colSpan={6} className="px-3 text-fg-muted">
                  Nenhum worker registrado ainda — o market-worker precisa estar rodando.
                </td>
              </tr>
            ) : (
              workers.map((worker) => (
                <tr key={`${worker.role}:${worker.instance}`} className="h-8 border-t border-border">
                  <td className="px-3 text-fg">{worker.role}</td>
                  <td className="px-3 font-mono text-fg-muted">{worker.instance}</td>
                  <td className="px-3">
                    <Badge variant={STATUS_VARIANT[worker.status]}>{worker.status}</Badge>
                  </td>
                  <td className="px-3 text-right font-mono tabular-nums text-fg-muted">
                    <AgeCell ts={worker.ts} />
                  </td>
                  <td className="px-3 text-right font-mono tabular-nums text-fg-muted">{worker.errors}</td>
                  <td className="px-3 font-mono text-fg-muted">{worker.version ?? "--"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full text-left text-[13px]">
          <thead className="bg-bg-overlay text-xs text-fg-muted">
            <tr>
              <th className="h-8 px-3 font-medium">Exchange</th>
              <th className="h-8 px-3 font-medium">WS</th>
              <th className="h-8 px-3 font-medium text-right">Monitorados</th>
              <th className="h-8 px-3 font-medium text-right">Reconexões</th>
              <th className="h-8 px-3 font-medium text-right">Gaps abertos</th>
            </tr>
          </thead>
          <tbody>
            {exchanges.length === 0 ? (
              <tr className="h-8 border-t border-border">
                <td colSpan={5} className="px-3 text-fg-muted">
                  Nenhuma exchange reportando heartbeat ainda.
                </td>
              </tr>
            ) : (
              exchanges.map((exchange) => (
                <tr key={exchange.instance} className="h-8 border-t border-border">
                  <td className="px-3 text-fg">{exchange.instance}</td>
                  <td className="px-3 text-fg-muted">{(exchange.ws_state ?? "unavailable").toUpperCase()}</td>
                  <td className="px-3 text-right font-mono tabular-nums text-fg-muted">{exchange.markets_monitored ?? "--"}</td>
                  <td className="px-3 text-right font-mono tabular-nums text-fg-muted">{exchange.reconnects ?? "--"}</td>
                  <td className="px-3 text-right font-mono tabular-nums text-fg-muted">{exchange.open_gaps ?? "--"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
