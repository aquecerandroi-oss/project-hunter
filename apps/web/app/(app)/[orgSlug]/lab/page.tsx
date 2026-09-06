import { notFound } from "next/navigation";

import { AutoRefresh } from "@/components/auto-refresh";
import { LabError } from "@/components/lab/lab-error";
import { LabFilters } from "@/components/lab/lab-filters";
import { LabHeader } from "@/components/lab/lab-header";
import { LabSignalsTable } from "@/components/lab/lab-signals-table";
import { LabTabs } from "@/components/lab/lab-tabs";
import { LabVersionCard } from "@/components/lab/lab-version-card";
import { LabVersionsEmpty } from "@/components/lab/lab-versions-empty";
import { DEFAULT_AUTO_REFRESH_INTERVAL_MS } from "@/lib/auto-refresh-interval";
import { isApiError } from "@/lib/api-error";
import { getLabSignals, getLabSummary, listLabVersions } from "@/lib/api/lab";
import type { LabSignalsParams } from "@/lib/api/lab";
import type { LabSignalsPage, LabSummaryOut, LabVersionsOut } from "@/lib/api/lab-types";
import { resolveOrgContext } from "@/lib/api/org-context";
import { logger } from "@/lib/logger";

export interface LabPageProps {
  params: Promise<{ orgSlug: string }>;
  searchParams: Promise<{ window?: string; cohort?: string; version?: string }>;
}

// No realtime channel and no per-response `stale_after_ms` of its own (this
// is a research endpoint, not live market data) -- same fallback cadence
// `system/page.tsx` uses, plus `AutoRefresh` for an already-open tab
// (T1.5 review F2's fix, reused here).
export const revalidate = 15;

// Signals list is fetched once per page load at the API's own max page size
// (`MAX_PAGE_SIZE = 200`, `repositories/base.py`) so the virtualized table
// starts with a real >= 200-row budget, exactly like `/markets` (T1.5 M1).
const SIGNALS_INITIAL_LIMIT = 200;

const WINDOWS = ["7d", "30d", "all"] as const;
type LabWindow = (typeof WINDOWS)[number];

function isWindow(value: string | undefined): value is LabWindow {
  return WINDOWS.includes(value as LabWindow);
}

type LabLoad =
  | { ok: true; summary: LabSummaryOut; versions: LabVersionsOut; signals: LabSignalsPage }
  | { ok: false; reason: string };

/**
 * Fetches, never constructs JSX (same split as `markets/page.tsx`'s
 * `loadMarkets`: a try/catch around JSX can't actually catch a rendering
 * error, since React doesn't render synchronously inside it).
 */
async function loadLab(window: LabWindow, cohort: string, versionId: string | undefined): Promise<LabLoad> {
  try {
    const signalsParams: LabSignalsParams = { cohort, limit: SIGNALS_INITIAL_LIMIT };
    if (versionId) signalsParams.strategy_version_id = versionId;
    const [summary, versions, signals] = await Promise.all([
      getLabSummary({ window, cohort }),
      listLabVersions(),
      getLabSignals(signalsParams),
    ]);
    return { ok: true, summary, versions, signals };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    logger.error("lab_page_load_failed", { error: reason });
    return { ok: false, reason };
  }
}

/** `/[orgSlug]/lab` (docs/plans/SHADOW-LAB.md, S3): the Shadow tab -- hypothetical, no-capital decisions and their tracked outcomes over real M1 data. */
export default async function LabPage({ params, searchParams }: LabPageProps) {
  const { orgSlug } = await params;
  const membership = await resolveOrgContext(orgSlug);
  if (!membership) notFound();

  const sp = await searchParams;
  const window: LabWindow = isWindow(sp.window) ? sp.window : "30d";
  const cohort = sp.cohort?.trim() || "prospective";
  const versionId = sp.version || undefined;

  const result = await loadLab(window, cohort, versionId);

  return (
    <div className="flex flex-col gap-4">
      <AutoRefresh intervalMs={DEFAULT_AUTO_REFRESH_INTERVAL_MS} />
      <h1 className="text-xl font-semibold text-fg">Lab</h1>
      <LabTabs />
      {!result.ok ? (
        <LabError reason={result.reason} />
      ) : (
        <LabPageBody orgSlug={orgSlug} window={window} cohort={cohort} versionId={versionId} {...result} />
      )}
    </div>
  );
}

interface LabPageBodyProps {
  orgSlug: string;
  window: LabWindow;
  cohort: string;
  versionId: string | undefined;
  summary: LabSummaryOut;
  versions: LabVersionsOut;
  signals: LabSignalsPage;
}

function LabPageBody({ orgSlug, window, cohort, versionId, summary, versions, signals }: LabPageBodyProps) {
  const versionLabelById: Record<string, string> = {};
  for (const v of versions.items) versionLabelById[v.strategy_version_id] = `${v.strategy_key}/${v.version}`;
  for (const v of summary.versions) versionLabelById[v.strategy_version_id] ??= `${v.strategy_key}/${v.version}`;

  // `superseded_by` only exists on the `/versions` catalogue item (best-effort,
  // regex-reconstructed from `changelog` -- contract-S3-lab.md), not on the
  // `/summary` item; resolved to a label only when the target is also
  // rendered on this page (so the `#version-<id>` anchor always has a match).
  const catalogueById = new Map(versions.items.map((v) => [v.strategy_version_id, v]));

  const filterVersionOptions = summary.versions.map((v) => ({
    id: v.strategy_version_id,
    label: `${v.strategy_key}/${v.version} (${v.status})`,
  }));

  return (
    <>
      <LabHeader asOf={summary.as_of} versions={summary.versions} />
      <LabFilters window={window} cohort={cohort} versionId={versionId ?? null} versions={filterVersionOptions} />

      <section className="flex flex-col gap-4">
        {summary.versions.length === 0 ? (
          <LabVersionsEmpty />
        ) : (
          summary.versions.map((v) => {
            const supersededById = catalogueById.get(v.strategy_version_id)?.superseded_by ?? null;
            const supersededBy =
              supersededById && versionLabelById[supersededById]
                ? { id: supersededById, label: versionLabelById[supersededById] }
                : null;
            return <LabVersionCard key={v.strategy_version_id} version={v} supersededBy={supersededBy} />;
          })
        )}
      </section>

      <LabSignalsTable
        orgSlug={orgSlug}
        initialItems={signals.items}
        initialCursor={signals.next_cursor}
        baseParams={{ cohort, limit: SIGNALS_INITIAL_LIMIT, ...(versionId ? { strategy_version_id: versionId } : {}) }}
        versionLabelById={versionLabelById}
        cohort={cohort}
      />
    </>
  );
}
