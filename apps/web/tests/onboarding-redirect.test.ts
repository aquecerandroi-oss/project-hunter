import { describe, expect, it } from "vitest";

import { resolveOnboardingRedirect } from "@/lib/onboarding-redirect";

describe("resolveOnboardingRedirect (org layout gating: app/(app)/[orgSlug]/layout.tsx)", () => {
  it("redirects to the wizard, resuming this org, when onboarding is not completed", () => {
    expect(resolveOnboardingRedirect("acme", false, "/acme/dashboard")).toBe("/onboarding?org=acme");
  });

  it("does not redirect once onboarding is completed", () => {
    expect(resolveOnboardingRedirect("acme", true, "/acme/dashboard")).toBeNull();
  });

  it("does not redirect when the pathname is already an onboarding route", () => {
    expect(resolveOnboardingRedirect("acme", false, "/onboarding")).toBeNull();
    expect(resolveOnboardingRedirect("acme", false, "/onboarding/2")).toBeNull();
  });

  it("builds the redirect target from the given org slug", () => {
    expect(resolveOnboardingRedirect("other-org", false, "/other-org/settings/profile")).toBe(
      "/onboarding?org=other-org",
    );
  });
});
