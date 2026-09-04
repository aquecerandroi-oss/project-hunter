import { SignUp } from "@clerk/nextjs";

import { clerkAppearance } from "@/lib/clerk-appearance";

export default function SignUpPage() {
  return (
    <main className="flex min-h-dvh items-center justify-center bg-background px-4">
      <SignUp appearance={clerkAppearance} />
    </main>
  );
}
