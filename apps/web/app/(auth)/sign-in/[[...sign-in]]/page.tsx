import { SignIn } from "@clerk/nextjs";

import { clerkAppearance } from "@/lib/clerk-appearance";

export default function SignInPage() {
  return (
    <main className="flex min-h-dvh items-center justify-center bg-bg px-4">
      <SignIn appearance={clerkAppearance} />
    </main>
  );
}
