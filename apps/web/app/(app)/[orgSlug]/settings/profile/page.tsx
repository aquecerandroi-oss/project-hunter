import { UserProfile } from "@clerk/nextjs";

import { clerkAppearance } from "@/lib/clerk-appearance";

/** Settings > Profile -- Clerk owns identity (name, avatar, email, connected accounts). */
export default function ProfileSettingsPage() {
  return <UserProfile routing="hash" appearance={clerkAppearance} />;
}
