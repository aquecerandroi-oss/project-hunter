"use client";

import { usePathname, useRouter } from "next/navigation";

export interface LabFilterVersionOption {
  id: string;
  label: string;
}

export interface LabFiltersProps {
  window: "7d" | "30d" | "all";
  cohort: string;
  versionId: string | null;
  versions: LabFilterVersionOption[];
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
 */
export function LabFilters({ window: activeWindow, cohort, versionId, versions }: LabFiltersProps) {
  const router = useRouter();
  const pathname = usePathname();

  function navigate(next: { window?: string; cohort?: string; version?: string | null }): void {
    const params = new URLSearchParams();
    params.set("window", next.window ?? activeWindow);
    const nextCohort = next.cohort ?? cohort;
    if (nextCohort && nextCohort !== "prospective") params.set("cohort", nextCohort);
    const nextVersion = next.version === undefined ? versionId : next.version;
    if (nextVersion) params.set("version", nextVersion);
    router.push(`${pathname}?${params.toString()}`);
  }

  return (
    <div className="flex flex-wrap items-end gap-4 text-sm">
      <label className="flex flex-col gap-1">
        <span className="text-xs text-fg-muted">Janela do resumo</span>
        <select
          value={activeWindow}
          onChange={(e) => navigate({ window: e.target.value })}
          className="h-8 rounded-md border border-border bg-bg-overlay px-2 text-[13px] text-fg"
        >
          {WINDOW_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-fg-muted">Cohort</span>
        <input
          type="text"
          defaultValue={cohort}
          onBlur={(e) => navigate({ cohort: e.target.value.trim() || "prospective" })}
          aria-label="Cohort"
          className="h-8 w-48 rounded-md border border-border bg-bg-overlay px-2 text-[13px] text-fg"
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-fg-muted">Versão (lista de sinais)</span>
        <select
          value={versionId ?? ""}
          onChange={(e) => navigate({ version: e.target.value || null })}
          className="h-8 rounded-md border border-border bg-bg-overlay px-2 text-[13px] text-fg"
        >
          <option value="">Todas as versões</option>
          {versions.map((v) => (
            <option key={v.id} value={v.id}>
              {v.label}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
