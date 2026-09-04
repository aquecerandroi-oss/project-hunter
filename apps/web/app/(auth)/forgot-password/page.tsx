import { SignIn } from "@clerk/nextjs";

import { clerkAppearance } from "@/lib/clerk-appearance";

/**
 * There is no separate Clerk "forgot password" component -- the reset flow
 * lives inside `<SignIn />` itself ("Forgot password?" -> code -> new
 * password). Mounting it at this path keeps `/forgot-password` (linked from
 * the sign-in screen and public in `middleware.ts`) a real, working page
 * instead of a stub.
 */
export default function ForgotPasswordPage() {
  return (
    <main className="flex min-h-dvh items-center justify-center bg-background px-4">
      <SignIn path="/forgot-password" routing="path" appearance={clerkAppearance} />
    </main>
  );
}
