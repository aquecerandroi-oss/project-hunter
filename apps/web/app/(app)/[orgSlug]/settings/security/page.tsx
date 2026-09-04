import { UserProfile } from "@clerk/nextjs";

import { PlannedBadge } from "@/components/layout/planned-badge";
import { clerkAppearance } from "@/lib/clerk-appearance";

/**
 * Settings > Security -- sessions/passwords are Clerk's (`UserProfile`'s
 * security tab). API keys are a real, dated gap, not a stub: docs/PRODUCT.md
 * §4 lists `/settings/api` as unlocking in Fase 2, after `api_access`
 * becomes a real entitlement (§5) -- there is nothing to configure yet.
 */
export default function SecuritySettingsPage() {
  return (
    <div className="flex flex-col gap-4">
      <UserProfile routing="hash" appearance={clerkAppearance} />
      <div className="flex items-center gap-2 rounded-md border border-dashed border-border p-3 text-sm text-fg-muted">
        API keys <PlannedBadge milestone="Fase 2" />
      </div>
    </div>
  );
}
