import { notFound } from "next/navigation";

import { AutoRefresh } from "@/components/auto-refresh";
import { ExecutionPaperCard } from "@/components/system/execution-paper-card";
import { FeatureFlagsTable } from "@/components/system/feature-flags-table";
import { LatencyPanel } from "@/components/system/latency-panel";
import { ReadinessPanel } from "@/components/system/readiness-panel";
import { SystemInfoCard } from "@/components/system/system-info-card";
import { WorkersTable } from "@/components/system/workers-table";
import { SectionUnavailable } from "@/components/ui/section-unavailable";
import { isApiError } from "@/lib/api-error";
import { getLatency } from "@/lib/api/latency";
import type { LatencyOut } from "@/lib/api/latency-types";
import { resolveOrgContext } from "@/lib/api/org-context";
import { getWorkers, ready, systemInfo } from "@/lib/api/system";
import type { SystemInfo, WorkerHeartbeat } from "@/lib/api/types";
import { logger } from "@/lib/logger";

export interface SystemPageProps {
  params: Promise<{ orgSlug: string }>;
}

// Best-effort freshness for a page with no realtime channel of its own;
// `AutoRefresh` below (T1.5 review F2) is what actually keeps an
// already-open tab from reading as stale -- `revalidate` only helps the
// *next* request. `ReadinessPanel` also still re-checks on demand via a real
// Server Action (see its own docstring).
export const revalidate = 15;

type WorkersLoad = { ok: true; workers: WorkerHeartbeat[] } | { ok: false; reason: string };
type SystemInfoLoad = { ok: true; info: SystemInfo } | { ok: false; reason: string };
type LatencyLoad = { ok: true; latency: LatencyOut } | { ok: false; reason: string };

/**
 * A fetch failure (API down, bad `API_URL`) is NOT the same fact as "zero
 * workers reporting" -- conflating the two would show "nenhum worker
 * registrado" for a real outage, which reads as "nothing is wrong, nothing
 * is running" instead of "something is wrong". `WorkersTable` itself still
 * renders the honest empty row for a genuinely empty (successful) response.
 */
async function loadWorkers(): Promise<WorkersLoad> {
  try {
    return { ok: true, workers: await getWorkers() };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    logger.error("system_workers_load_failed", { error: reason });
    return { ok: false, reason };
  }
}

/**
 * Isolated from `loadWorkers`/`ready()` (T1.5 review F3): `systemInfo()`,
 * `ready()` and `getWorkers()` used to sit in one `Promise.all`, so a single
 * `/api/v1/system/info` outage rejected the whole page before Workers or
 * Readiness ever got a chance to render their own honest state -- the user
 * got a framework error boundary instead of the per-section unavailable
 * message this page promises. `ready()` already fails open (see its own
 * docstring, `lib/api/system.ts`) so it never needs this wrapper.
 */
async function loadSystemInfo(): Promise<SystemInfoLoad> {
  try {
    return { ok: true, info: await systemInfo() };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    logger.error("system_info_load_failed", { error: reason });
    return { ok: false, reason };
  }
}

/**
 * Isolated the same way `loadWorkers`/`loadSystemInfo` are (T1.5 review F3):
 * a `/system/latency` outage must not take down the rest of the page, and
 * "the API call failed" is not the same fact as "every hop is `unknown`" --
 * conflating the two would show a fabricated all-unknown budget for a real
 * outage instead of the honest per-section failure box.
 */
async function loadLatency(): Promise<LatencyLoad> {
  try {
    return { ok: true, latency: await getLatency() };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    logger.error("system_latency_load_failed", { error: reason });
    return { ok: false, reason };
  }
}

/** `/system` (docs/PRODUCT.md §4, available from M0) -- API/DB/Redis health, feature flags, honest worker status. */
export default async function SystemPage({ params }: SystemPageProps) {
  const { orgSlug } = await params;
  const membership = await resolveOrgContext(orgSlug);
  if (!membership) notFound();

  const [infoLoad, readiness, workersLoad, latencyLoad] = await Promise.all([
    loadSystemInfo(),
    ready(),
    loadWorkers(),
    loadLatency(),
  ]);

  return (
    <div className="flex flex-col gap-4">
      <AutoRefresh />
      <h1 className="text-xl font-semibold text-fg">System</h1>
      <div className="grid gap-4 md:grid-cols-2">
        {infoLoad.ok ? <SystemInfoCard info={infoLoad.info} /> : <SectionUnavailable title="API" reason={infoLoad.reason} />}
        <ReadinessPanel initial={readiness} />
        {infoLoad.ok ? (
          <FeatureFlagsTable features={infoLoad.info.features} />
        ) : (
          <SectionUnavailable title="Feature flags" reason={infoLoad.reason} />
        )}
      </div>
      {latencyLoad.ok ? <LatencyPanel data={latencyLoad.latency} /> : <SectionUnavailable title="Latência" reason={latencyLoad.reason} />}
      <section>
        <h2 className="mb-2 text-xs font-medium uppercase tracking-wide text-fg-muted">Workers</h2>
        {workersLoad.ok ? (
          <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
            <WorkersTable workers={workersLoad.workers} />
            {/*
              T3.44: `role === "execution"` alone matches TWO rows -- the
              generic per-process liveness heartbeat every `WorkerRuntime`
              writes (`hb:execution:{hostname}:{pid}`, only `ts`/`errors`/
              `version`) AND the execution-worker's own aggregate
              (`hb:execution:paper`, the T3.13/T3.14 fields this card reads).
              `scan_heartbeats` sorts by `(role, instance)`
              (`services/system_status.py`), and the generic row's anonymized
              instance is a lowercase hex digest -- always sorting before the
              literal string "paper" -- so the old `.find(role === "execution")`
              deterministically picked the WRONG row: `worker` was truthy (no
              "sem heartbeat" empty state) but every T3.13 field on it was
              `undefined`, rendering "indisponível" for all of them at once.
              Matching on `instance === "paper"` too picks the actual
              aggregate.
            */}
            <ExecutionPaperCard
              worker={workersLoad.workers.find((worker) => worker.role === "execution" && worker.instance === "paper") ?? null}
            />
          </div>
        ) : (
          <SectionUnavailable title="Workers" reason={workersLoad.reason} />
        )}
      </section>
    </div>
  );
}
