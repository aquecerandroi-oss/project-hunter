import { redirect } from "next/navigation";

import { AcceptInviteCard } from "@/components/invitations/accept-invite-card";
import { getServerSession } from "@/lib/server/auth";

export interface AcceptInvitePageProps {
  searchParams: Promise<{ token?: string }>;
}

/**
 * Landing page for an invitation link (`/accept-invite?token=<...>`, built by
 * `components/settings/invite-form.tsx`). `/accept-invite` is deliberately
 * *not* added to `middleware.ts`'s public allowlist, so an unauthenticated
 * visit is already bounced to sign-in (with `redirect_url` pointing back
 * here) by `auth.protect()` before this component ever runs -- the check
 * below is defense in depth, the same posture `app/(app)/[orgSlug]/layout.tsx`
 * takes for its own routes.
 */
export default async function AcceptInvitePage({ searchParams }: AcceptInvitePageProps) {
  const { token } = await searchParams;

  const session = await getServerSession();
  if (!session) {
    const back = `/accept-invite${token ? `?token=${encodeURIComponent(token)}` : ""}`;
    redirect(`/sign-in?redirect_url=${encodeURIComponent(back)}`);
  }

  return (
    <main className="flex min-h-dvh items-center justify-center bg-bg px-4">
      <AcceptInviteCard token={token ?? null} />
    </main>
  );
}
