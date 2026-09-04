import { notFound, redirect } from "next/navigation";

import { OnboardingWizard } from "@/components/onboarding/wizard";
import type { WizardStep } from "@/components/onboarding/wizard-state";
import { resolveOrgContext } from "@/lib/api/org-context";

export interface OnboardingPageProps {
  params: Promise<{ step?: string[] }>;
  searchParams: Promise<{ org?: string }>;
}

function parseStep(segments: string[] | undefined): WizardStep | undefined {
  const raw = segments?.[0];
  if (!raw) return undefined;
  const n = Number(raw);
  return n >= 1 && n <= 6 ? (n as WizardStep) : undefined;
}

/**
 * The six-step onboarding wizard (docs/PRODUCT.md §3). `?org=<slug>` resumes
 * an organization that already exists but hasn't finished onboarding --
 * `app/page.tsx` is what sends a signed-in user here with that query.
 * `[[...step]]` lets the current step show in the URL (bookmarkable/
 * refresh-safe); `components/onboarding/wizard.tsx` owns the actual state.
 */
export default async function OnboardingPage({ params, searchParams }: OnboardingPageProps) {
  const { step } = await params;
  const { org: orgSlug } = await searchParams;
  const initialStep = parseStep(step);

  if (!orgSlug) {
    return (
      <main className="flex min-h-dvh items-start justify-center bg-bg px-4 py-10 sm:items-center">
        <OnboardingWizard initialOrg={null} initialStep={initialStep} />
      </main>
    );
  }

  const membership = await resolveOrgContext(orgSlug);
  if (!membership) notFound();
  if (membership.onboarding.completed) redirect(`/${orgSlug}/dashboard`);

  // No workspace to onboard onto (shouldn't happen -- `createOrganization`
  // always creates one) -- fall back to a fresh, non-resumed wizard rather
  // than a broken resume.
  const initialOrg = membership.onboarding.workspace_id
    ? { orgSlug, orgId: membership.organization.id, workspaceId: membership.onboarding.workspace_id }
    : null;

  return (
    <main className="flex min-h-dvh items-start justify-center bg-bg px-4 py-10 sm:items-center">
      <OnboardingWizard initialOrg={initialOrg} initialStep={initialStep} />
    </main>
  );
}
