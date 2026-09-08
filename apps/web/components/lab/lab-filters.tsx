"use client";

import { usePathname, useRouter } from "next/navigation";

import { Select } from "@/components/ui/select";
import type { LabSignalsPageSize, LabSignalsState } from "@/lib/api/lab-types";

export interface LabFilterVersionOption {
  id: string;
  label: string;
}

export interface LabFiltersProps {
  window: "7d" | "30d" | "all";
  cohort: string;
  versionId: string | null;
  versions: LabFilterVersionOption[];
  /** Distinct cohorts present in the currently loaded signals page (brief T3.24b item [3]) -- `"prospective"` is always offered even when absent from the page, since it is the endpoint's own default. */
  cohorts: string[];
  /**
   * T3.37: the signals table's own `state`/`page_size`, preserved across a
   * window/cohort/version change (never reset to the tab/page-size default
   * just because a filter changed) -- optional so callers that predate T3.37
   * (`components/design/lab-hierarchy-showcase.tsx`) keep working unchanged.
   * The cursor path is intentionally never preserved here: a different
   * cohort/window/version is a different dataset, so it always goes back to
   * page 1.
   */
  state?: LabSignalsState;
  pageSize?: LabSignalsPageSize;
}

const WINDOW_OPTIONS: Array<{ value: "7d" | "30d" | "all"; label: string }> = [
  { value: "7d", label: "7 dias" },
  { value: "30d", label: "30 dias" },
  { value: "all", label: "Tudo" },
];

/**
 * Navigates by rewriting the page's own query string -- the Server
 * Component (`app/(app)/[orgSlug]/lab/page.tsx`) reads `searchParams` and
 * refetches `summary`/`signals` accordingly, so filter state lives in the
 * URL (shareable, back-button-safe), never in client-only state that a
 * refresh would drop.
 *
 * `window`/`cohort` only affect the summary (`GET .../summary`); `version`
 * scopes the signals list below (`GET .../signals?strategy_version_id=`).
 * The signals endpoint does not accept `window`/`as_of` at all
 * (contract-S3-lab.md, `routers/lab.py::list_signals`) -- labelled
 * separately in `LabSignalsTable` so the two lists never look like they
 * share one clock (Astra, S3b hierarchy review, must-fix).
 *
 * `Coorte` is a `<select>` since T3.24b item [3] (X6-class fix, T3.24a): a
 * free-text input let a reader type an unreachable cohort string with no
 * feedback -- the options are exactly the cohorts this page already knows
 * about (`prospective`, plus whatever else the loaded signals page shows).
 */
export function LabFilters({ window: activeWindow, cohort, versionId, versions, cohorts, state, pageSize }: LabFiltersProps) {
  const router = useRouter();
  const pathname = usePathname();

  function navigate(next: { window?: string; cohort?: string; version?: string | null }): void {
    const params = new URLSearchParams();
    params.set("window", next.window ?? activeWindow);
    const nextCohort = next.cohort ?? cohort;
    if (nextCohort && nextCohort !== "prospective") params.set("cohort", nextCohort);
    const nextVersion = next.version === undefined ? versionId : next.version;
    if (nextVersion) params.set("version", nextVersion);
    // Preserved as-is; the cursor path (`c`) is deliberately never carried
    // over -- a different window/cohort/version is a different dataset, so
    // the signals table always goes back to page 1 (T3.37).
    if (state) params.set("state", state);
    if (pageSize) params.set("page_size", String(pageSize));
    router.push(`${pathname}?${params.toString()}`);
  }

  const cohortOptions = Array.from(new Set(["prospective", ...cohorts]));

  return (
    <div className="flex flex-wrap items-end gap-4 text-sm">
      <label className="flex flex-col gap-1">
        <span className="text-xs text-fg-muted">Janela do resumo</span>
        <Select value={activeWindow} onChange={(e) => navigate({ window: e.target.value })}>
          {WINDOW_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </Select>
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-fg-muted">Coorte</span>
        <Select value={cohort} onChange={(e) => navigate({ cohort: e.target.value })} aria-label="Coorte">
          {cohortOptions.map((value) => (
            <option key={value} value={value}>
              {value === "prospective" ? "prospective (padrão)" : value}
            </option>
          ))}
        </Select>
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-fg-muted">Versão (lista de sinais)</span>
        <Select value={versionId ?? ""} onChange={(e) => navigate({ version: e.target.value || null })}>
          <option value="">Todas as versões</option>
          {versions.map((v) => (
            <option key={v.id} value={v.id}>
              {v.label}
            </option>
          ))}
        </Select>
      </label>
    </div>
  );
}
