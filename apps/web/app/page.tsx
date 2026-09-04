import { redirect } from "next/navigation";

import { me } from "@/lib/api/me";
import { getServerSession } from "@/lib/server/auth";

/**
 * The one router the app shell needs (docs/PRODUCT.md §3, T09):
 * - signed out -> `/sign-in`.
 * - signed in, no memberships yet -> `/onboarding` (step 1, create the org).
 * - signed in, a membership hasn't finished onboarding -> resume it at
 *   `/onboarding?org=<slug>` (wizard-state.ts skips straight to step 2 for
 *   that org).
 * - otherwise -> the first membership's dashboard.
 */
export default async function HomePage(): Promise<never> {
  const session = await getServerSession();
  if (!session) redirect("/sign-in");

  const { memberships } = await me();
  if (memberships.length === 0) redirect("/onboarding");

  const unfinished = memberships.find((m) => !m.onboarding.completed);
  if (unfinished) redirect(`/onboarding?org=${unfinished.organization.slug}`);

  const [first] = memberships;
  if (!first) redirect("/onboarding"); // unreachable: memberships.length > 0 was checked above
  redirect(`/${first.organization.slug}/dashboard`);
}
