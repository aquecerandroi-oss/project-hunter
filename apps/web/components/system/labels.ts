/**
 * `/system`'s plain-Portuguese vocabulary (DESIGN-5, "sem backstage na
 * copy"). `role`/`ws_state` travel as plain `string` in `WorkerHeartbeatOut`
 * (no literal union in the OpenAPI contract), so `WORKER_ROLE_VALUES` below
 * -- not the TS type -- is what `tests/system-labels.test.ts` iterates for
 * exhaustiveness; an unrecognized role still renders (falls back to itself)
 * rather than disappearing.
 */
import type { WorkerStatus } from "@/lib/api/types";

export const WORKER_ROLE_VALUES = ["market", "scanner", "strategy", "execution"] as const;
export type WorkerRoleValue = (typeof WORKER_ROLE_VALUES)[number];

const ROLE_LABEL: Record<WorkerRoleValue, string> = {
  market: "Mercados",
  scanner: "Scanner",
  strategy: "Estratégias",
  execution: "Execução",
};

export function workerRoleLabel(role: string): string {
  return ROLE_LABEL[role as WorkerRoleValue] ?? role;
}

export const WORKER_STATUS_VALUES: WorkerStatus[] = ["alive", "late", "dead"];

const WORKER_STATUS_LABEL: Record<WorkerStatus, string> = {
  alive: "vivo",
  late: "atrasado",
  dead: "morto",
};

export function workerStatusLabel(status: WorkerStatus): string {
  return WORKER_STATUS_LABEL[status];
}

/** `ReadinessPanel`'s overall verdict -- "Ready"/"Not Ready" translated directly. */
export function readyLabel(ready: boolean): string {
  return ready ? "Pronto" : "Não pronto";
}
