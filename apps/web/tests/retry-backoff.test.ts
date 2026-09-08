import { describe, expect, it } from "vitest";

import { backoffDelayMs, MAX_AUTO_RETRIES } from "@/lib/retry-backoff";

describe("backoffDelayMs: doubles each attempt, starting at 2s (brief T3.28b)", () => {
  it("returns 2s for the 1st attempt", () => {
    expect(backoffDelayMs(1)).toBe(2000);
  });

  it("returns 4s for the 2nd attempt", () => {
    expect(backoffDelayMs(2)).toBe(4000);
  });

  it("returns 8s for the 3rd attempt", () => {
    expect(backoffDelayMs(3)).toBe(8000);
  });

  it("caps auto-retries at 3", () => {
    expect(MAX_AUTO_RETRIES).toBe(3);
  });
});
