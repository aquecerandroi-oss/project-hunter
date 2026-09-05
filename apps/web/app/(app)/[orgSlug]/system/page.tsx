import { notFound } from "next/navigation";

import { AutoRefresh } from "@/components/auto-refresh";
import { FeatureFlagsTable } from "@/components/system/feature-flags-table";
import { ReadinessPanel } from "@/components/system/readiness-panel";
import { SystemInfoCard } from "@/components/system/system-info-card";
import { WorkersTable } from "@/components/system/workers-table";
import { isApiError } from "@/lib/api-error";
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

function UnavailableSection({ title, reason }: { title: string; reason: string }) {
  return (
    <section className="rounded-lg border border-dashed border-red/40 bg-bg-elevated p-4">
      <h2 className="text-xs font-medium uppercase tracking-wide text-fg-muted">{title}</h2>
      <p className="mt-2 text-sm text-fg">Indisponível: {reason}</p>
    </section>
  );
}

/** `/system` (docs/PRODUCT.md §4, available from M0) -- API/DB/Redis health, feature flags, honest worker status. */
export default async function SystemPage({ params }: SystemPageProps) {
  const { orgSlug } = await params;
  const membership = await resolveOrgContext(orgSlug);
  if (!membership) notFound();

  const [infoLoad, readiness, workersLoad] = await Promise.all([loadSystemInfo(), ready(), loadWorkers()]);

  return (
    <div className="flex flex-col gap-4">
      <AutoRefresh />
      <h1 className="text-xl font-semibold text-fg">System</h1>
      <div className="grid gap-4 md:grid-cols-2">
        {infoLoad.ok ? <SystemInfoCard info={infoLoad.info} /> : <UnavailableSection title="API" reason={infoLoad.reason} />}
        <ReadinessPanel initial={readiness} />
        {infoLoad.ok ? (
          <FeatureFlagsTable features={infoLoad.info.features} />
        ) : (
          <UnavailableSection title="Feature flags" reason={infoLoad.reason} />
        )}
      </div>
      <section>
        <h2 className="mb-2 text-xs font-medium uppercase tracking-wide text-fg-muted">Workers</h2>
        {workersLoad.ok ? (
          <WorkersTable workers={workersLoad.workers} />
        ) : (
          <p className="rounded-md border border-dashed border-red/40 bg-bg-elevated p-4 text-sm text-fg">
            Workers indisponível: {workersLoad.reason}
          </p>
        )}
      </section>
    </div>
  );
}
