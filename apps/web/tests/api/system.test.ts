import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// `server-only` throws when imported outside Next's real "react-server"
// build condition, which Vitest never sets (see tests/invitations-actions.test.ts).
vi.mock("server-only", () => ({}));

// `system.ts` imports `apiFetch` from `@/lib/server/api` for its other
// exports (`getWorkers`/`systemInfo`/`getMarketStatus`), which transitively
// pulls in Clerk's server SDK -- `ready()` itself never calls `apiFetch`, so
// this mock only exists to keep that unrelated import graph out of a test
// that has nothing to do with it.
vi.mock("@/lib/server/api", () => ({ apiFetch: vi.fn() }));

import { READY_CHECK_NOT_CONFIGURED, ready, wasReadyCheckAttempted } from "@/lib/api/system";

const originalApiUrl = process.env.API_URL;
const originalFetch = global.fetch;

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  process.env.API_URL = originalApiUrl;
  global.fetch = originalFetch;
});

describe("ready(): never throws past the caller's own per-section isolation (H7)", () => {
  it("resolves to a distinct 'not configured' reading instead of rejecting when API_URL is unset", async () => {
    delete process.env.API_URL;

    // The bug: `ready()` used to `throw` on a missing `API_URL` BEFORE its
    // own `try`, so the rejection escaped straight out of the System page's
    // `Promise.all` -- none of the other isolated per-section messages ever
    // got a chance to render. This must resolve, never reject.
    //
    // T1.5b Astra must-fix #1: this used to collapse into the same
    // "unreachable" detail as a real network failure, which made `topbar.tsx`
    // /`system-health-line.tsx`'s "sem verificação" state unreachable through
    // the real loader -- only a hand-mocked `null` ever exercised it.
    const status = await ready();
    expect(status).toEqual({
      database: false,
      redis: false,
      database_detail: READY_CHECK_NOT_CONFIGURED,
      redis_detail: READY_CHECK_NOT_CONFIGURED,
    });
    expect(wasReadyCheckAttempted(status)).toBe(false);
  });

  it("still resolves to an honest 'down' reading when the fetch itself throws (network down), distinct from 'not configured'", async () => {
    process.env.API_URL = "http://api.internal";
    global.fetch = vi.fn().mockRejectedValue(new Error("ECONNREFUSED")) as unknown as typeof fetch;

    const status = await ready();
    expect(status).toEqual({
      database: false,
      redis: false,
      database_detail: "unreachable",
      redis_detail: "unreachable",
    });
    expect(wasReadyCheckAttempted(status)).toBe(true);
  });

  it("passes through the real body on a successful check", async () => {
    process.env.API_URL = "http://api.internal";
    const body = { database: true, redis: true };
    global.fetch = vi.fn().mockResolvedValue({ json: async () => body } as Response) as unknown as typeof fetch;

    await expect(ready()).resolves.toEqual(body);
  });
});
