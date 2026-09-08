import { LabFilters } from "@/components/lab/lab-filters";
import { LabSignalsTable } from "@/components/lab/lab-signals-table";
import { LabVersionCard } from "@/components/lab/lab-version-card";
import { LabVersionsEmpty } from "@/components/lab/lab-versions-empty";
import type { MoneyRuler } from "@/components/lab/lab-money";
import { SectionUnavailable } from "@/components/ui/section-unavailable";
import type { LabSignalsPage, LabSignalsPageSize, LabSignalsState, LabSummaryOut, LabVersionsOut } from "@/lib/api/lab-types";

export type LabSignalsLoad = { ok: true; page: LabSignalsPage } | { ok: false; reason: string };

export interface LabPageBodyProps {
  orgSlug: string;
  window: "7d" | "30d" | "all";
  cohort: string;
  versionId: string | undefined;
  state: LabSignalsState;
  pageSize: LabSignalsPageSize;
  cursorPath: string[];
  ruler: MoneyRuler;
  summary: LabSummaryOut;
  versions: LabVersionsOut;
  signalsResult: LabSignalsLoad;
}

function Eyebrow({ children }: { children: string }) {
  return <p className="text-xs font-medium uppercase tracking-wide text-fg-muted">{children}</p>;
}

/**
 * `/lab`'s "Sinais — Sombra" + "Versões (pesquisa)" sections -- split out of
 * `app/(app)/[orgSlug]/lab/page.tsx` (the Server Component itself) to keep
 * that file under the lint config's 350-line budget. Only rendered once
 * `loadLab` (summary + the frozen versions catalogue) has already succeeded;
 * `signalsResult` is its own independent outcome (T3.37) -- a signals-only
 * failure degrades to `SectionUnavailable` for just that section, never the
 * whole page.
 */
export function LabPageBody({
  orgSlug,
  window,
  cohort,
  versionId,
  state,
  pageSize,
  cursorPath,
  ruler,
  summary,
  versions,
  signalsResult,
}: LabPageBodyProps) {
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

  // Distinct cohorts discovered from the currently loaded signals page (brief
  // T3.24b item [3]) -- `LabFilters` always offers "prospective" itself even
  // when this list is empty (its own endpoint default), so a failed/empty
  // signals fetch never blocks the `<select>` from rendering.
  const cohorts = signalsResult.ok ? Array.from(new Set(signalsResult.page.items.map((s) => s.cohort))) : [];

  return (
    <>
      {/* Sinais — Sombra (brief T3.24b §2 item [3]): filters, segments,
          compact totals, table + panel all live under this one section, so
          the page reads as "one hierarchy" instead of three stacked
          summaries before the first signal row. */}
      <section className="flex flex-col gap-3">
        <Eyebrow>Sinais — Sombra</Eyebrow>
        <LabFilters
          window={window}
          cohort={cohort}
          versionId={versionId ?? null}
          versions={filterVersionOptions}
          cohorts={cohorts}
          state={state}
          pageSize={pageSize}
        />
        {signalsResult.ok ? (
          <LabSignalsTable
            orgSlug={orgSlug}
            items={signalsResult.page.items}
            totals={signalsResult.page.totals}
            page={signalsResult.page.page}
            pageSize={pageSize}
            nextCursor={signalsResult.page.next_cursor}
            cursorPath={cursorPath}
            state={state}
            window={window}
            cohort={cohort}
            versionId={versionId}
            versionLabelById={versionLabelById}
            ruler={ruler}
            summary={summary}
          />
        ) : (
          <SectionUnavailable title="Sinais — Sombra" reason={`falha ao carregar (${signalsResult.reason})`} />
        )}
      </section>

      <section className="flex flex-col gap-4">
        <Eyebrow>Versões (pesquisa)</Eyebrow>
        {summary.versions.length === 0 ? (
          <LabVersionsEmpty />
        ) : (
          summary.versions.map((v) => {
            const supersededById = catalogueById.get(v.strategy_version_id)?.superseded_by ?? null;
            const supersededBy =
              supersededById && versionLabelById[supersededById]
                ? { id: supersededById, label: versionLabelById[supersededById] }
                : null;
            return (
              <LabVersionCard
                key={v.strategy_version_id}
                version={v}
                supersededBy={supersededBy}
                openByDefault={versionId === v.strategy_version_id}
              />
            );
          })
        )}
      </section>
    </>
  );
}
