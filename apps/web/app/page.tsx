import { redirect } from "next/navigation";

import { getServerSession } from "@/lib/server/auth";

export default async function HomePage(): Promise<never> {
  const session = await getServerSession();
  // T09 will refine the signed-in target to the user's org slug once
  // onboarding/org selection exists; today it always lands on /onboarding.
  redirect(session ? "/onboarding" : "/sign-in");
}
