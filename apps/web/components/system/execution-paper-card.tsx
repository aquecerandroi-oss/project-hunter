"use client";

import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { formatSeconds, killSwitchBadgeVariant, killSwitchLabel } from "@/components/system/execution-paper-format";
import { SystemAsOf } from "@/components/system/system-as-of";
import { computeAgeMs, formatAge, heartbeatServerNowIso, useAgeTicker } from "@/hooks/useAgeTicker";
import type { WorkerHeartbeat } from "@/lib/api/types";
import { formatUsdt } from "@/lib/format";

export interface ExecutionPaperCardProps {
  /**
   * The `hb:execution:paper` row out of `/system/workers`
   * (`schemas/system.py`'s `WorkerHeartbeatOut`, T3.13/T3.14 fields), or
   * `null` when no such heartbeat has ever reported -- never fabricated.
   */
  worker: WorkerHeartbeat | null;
}

const UNAVAILABLE = "indisponível";

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-2 border-b border-border py-1.5 last:border-b-0">
      <span className="text-xs text-fg-muted">{label}</span>
      <span className="font-mono text-sm tabular-nums text-fg">{value}</span>
    </div>
  );
}

/** `null`/`undefined` -> "indisponível", never a fabricated 0 -- a real 0 (e.g. zero open positions) prints as "0". */
function countOrUnavailable(value: number | null | undefined): string {
  return value === null || value === undefined ? UNAVAILABLE : String(value);
}

/** `> 0` renders in an amber warning badge (brief: "proteções degradadas com destaque"); `0`/absent stays plain text. */
function degradedProtectionsCell(degraded: number | null | undefined): ReactNode {
  if (degraded !== null && degraded !== undefined && degraded > 0) return <Badge variant="warning">{degraded}</Badge>;
  return countOrUnavailable(degraded);
}

function equityCell(equity: string | null | undefined): string {
  return equity !== null && equity !== undefined ? formatUsdt(equity) : UNAVAILABLE;
}

function protectionDelayCell(delaySeconds: number | null | undefined): string {
  return delaySeconds !== null && delaySeconds !== undefined ? formatSeconds(delaySeconds) : UNAVAILABLE;
}

/** "sem geometria: a API arquivou, o motor não decide" (PIPELINE.md §8, `pending_request_without_geometry`) -- only when there is at least one, never for a real 0. */
function unreadableExplanation(unreadable: number | null | undefined): ReactNode {
  if (unreadable === null || unreadable === undefined || unreadable <= 0) return null;
  return (
    <p className="mt-2 text-xs text-warning">
      {unreadable} pedido{unreadable === 1 ? "" : "s"} sem geometria: a API arquivou, o motor não decide.
    </p>
  );
}

function killSwitchCell(killSwitch: string | null | undefined): ReactNode {
  if (killSwitch === null || killSwitch === undefined) return <span className="text-sm text-fg-muted">{UNAVAILABLE}</span>;
  return <Badge variant={killSwitchBadgeVariant(killSwitch)}>{killSwitchLabel(killSwitch)}</Badge>;
}

function autonomyLabelText(autonomy: boolean | null | undefined): string {
  if (autonomy === null || autonomy === undefined) return UNAVAILABLE;
  return autonomy ? "ligada" : "desligada";
}

/**
 * "há Xs" (ticking, `useAgeTicker`) plus the UTC+offset absolute stamp
 * (`SystemAsOf`, docs/DESIGN.md joint decision #9) -- the brief's "idade do
 * MTM/última leitura do kill switch... com o mesmo componente de tempo das
 * outras telas". A missing timestamp renders "indisponível", never a frozen
 * "0s" or an age computed against nothing.
 */
function AgeWithAsOf({ iso, now }: { iso: string | null | undefined; now: number }) {
  if (!iso) return <>{UNAVAILABLE}</>;
  const ageMs = computeAgeMs(iso, now);
  return (
    <span className="inline-flex flex-wrap items-baseline justify-end gap-1">
      <span>{ageMs !== null ? `há ${formatAge(ageMs)}` : UNAVAILABLE}</span>
      <span className="text-xs text-fg-subtle">
        (<SystemAsOf iso={iso} />)
      </span>
    </span>
  );
}

/**
 * "Execução paper" (T3.8c, brief item 1): the `hb:execution:paper`
 * heartbeat's eleven T3.13/T3.14 fields, next to `WorkersTable`'s generic
 * `execution/paper` row. Every optional field renders "indisponível" when
 * absent -- CLAUDE.md's "`null` never vira 0" -- never a silent zero, never
 * an invented number.
 */
export function ExecutionPaperCard({ worker }: ExecutionPaperCardProps) {
  // T3.16: `ts + age_s` is the server's own clock at scan time -- see
  // `heartbeatServerNowIso`'s docstring. `null` worker below never reaches
  // `useAgeTicker` with a real ts, so this stays `null` (viewer-clock
  // fallback) harmlessly in that branch -- the empty state renders before
  // any age is ever read.
  const { now } = useAgeTicker(worker ? heartbeatServerNowIso(worker.ts, worker.age_s) : null);

  if (!worker) {
    return (
      <section className="rounded-lg border border-dashed border-border bg-bg-elevated p-4">
        <h2 className="text-xs font-medium uppercase tracking-wide text-fg-muted">Execução paper</h2>
        <p className="mt-2 text-sm text-fg">Execution-worker: sem heartbeat.</p>
      </section>
    );
  }

  const killSwitch = worker.kill_switch;
  const blocked = killSwitch === "TRADING_DISABLED" || killSwitch === "EMERGENCY";
  const unreadable = worker.unreadable_requests;
  const autonomy = worker.paper_autonomy;

  return (
    <div className="rounded-md border border-border p-4" data-testid="execution-paper-card">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-fg">Execução paper</h3>
        {/* ENABLE_PAPER_AUTONOMY defaults to false (docs/DEPLOYMENT.md §3.2): "ligada" is the behavior change worth flagging, "desligada" is the expected/safe state. */}
        <Badge variant={autonomy === true ? "warning" : "default"}>Autonomia: {autonomyLabelText(autonomy)}</Badge>
      </div>

      <div className="mt-2">
        <Row label="Patrimônio" value={equityCell(worker.equity)} />
        <Row label="Posições abertas" value={countOrUnavailable(worker.open_positions)} />
        <Row label="Pedidos pendentes" value={countOrUnavailable(worker.pending_requests)} />
        <Row label="Pedidos ilegíveis" value={countOrUnavailable(unreadable)} />
        <Row label="Proteções degradadas" value={degradedProtectionsCell(worker.degraded_protections)} />
        <Row label="Atraso de proteção" value={protectionDelayCell(worker.protection_delay_s)} />
        <Row label="Idade do MTM" value={<AgeWithAsOf iso={worker.last_mtm} now={now} />} />
        <Row label="Última leitura do kill switch" value={<AgeWithAsOf iso={worker.last_kill_switch_read} now={now} />} />
        <Row label="Última proteção" value={<AgeWithAsOf iso={worker.last_protection} now={now} />} />
      </div>

      {unreadableExplanation(unreadable)}

      <div
        className={`mt-4 rounded-md border p-3 ${blocked ? "border-red bg-red-soft" : "border-border bg-bg-elevated"}`}
        data-testid="execution-kill-switch-panel"
      >
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-fg-muted">Kill switch efetivo</span>
          {killSwitchCell(killSwitch)}
        </div>
      </div>
    </div>
  );
}
