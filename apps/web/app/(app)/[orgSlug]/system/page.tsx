import { notFound } from "next/navigation";

import { FeatureFlagsTable } from "@/components/system/feature-flags-table";
import { ReadinessPanel } from "@/components/system/readiness-panel";
import { SystemInfoCard } from "@/components/system/system-info-card";
import { resolveOrgContext } from "@/lib/api/org-context";
import { ready, systemInfo } from "@/lib/api/system";

export interface SystemPageProps {
  params: Promise<{ orgSlug: string }>;
}

// Best-effort freshness for a page with no manual refresh; `ReadinessPanel`
// still re-checks on demand via a real Server Action (see its own docstring).
export const revalidate = 15;

/** `/system` (docs/PRODUCT.md §4, available from M0) -- API/DB/Redis health, feature flags, honest worker status. */
export default async function SystemPage({ params }: SystemPageProps) {
  const { orgSlug } = await params;
  const membership = await resolveOrgContext(orgSlug);
  if (!membership) notFound();

  const [info, readiness] = await Promise.all([systemInfo(), ready()]);

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold text-foreground">System</h1>
      <div className="grid gap-4 md:grid-cols-2">
        <SystemInfoCard info={info} />
        <ReadinessPanel initial={readiness} />
        <FeatureFlagsTable features={info.features} />
        <section className="rounded-lg border border-dashed border-border bg-surface-1 p-4">
          <h2 className="text-sm font-medium text-muted">Workers</h2>
          <p className="mt-2 text-sm text-foreground">Workers: nenhum processo registrado ainda (M1).</p>
        </section>
      </div>
    </div>
  );
}
