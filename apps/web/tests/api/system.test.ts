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

import { ready } from "@/lib/api/system";

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
  it("resolves to an honest 'down' reading instead of rejecting when API_URL is unset", async () => {
    delete process.env.API_URL;

    // The bug: `ready()` used to `throw` on a missing `API_URL` BEFORE its
    // own `try`, so the rejection escaped straight out of the System page's
    // `Promise.all` -- none of the other isolated per-section messages ever
    // got a chance to render. This must resolve, never reject.
    await expect(ready()).resolves.toEqual({
      database: false,
      redis: false,
      database_detail: "unreachable",
      redis_detail: "unreachable",
    });
  });

  it("still resolves to an honest 'down' reading when the fetch itself throws (network down)", async () => {
    process.env.API_URL = "http://api.internal";
    global.fetch = vi.fn().mockRejectedValue(new Error("ECONNREFUSED")) as unknown as typeof fetch;

    await expect(ready()).resolves.toEqual({
      database: false,
      redis: false,
      database_detail: "unreachable",
      redis_detail: "unreachable",
    });
  });

  it("passes through the real body on a successful check", async () => {
    process.env.API_URL = "http://api.internal";
    const body = { database: true, redis: true };
    global.fetch = vi.fn().mockResolvedValue({ json: async () => body } as Response) as unknown as typeof fetch;

    await expect(ready()).resolves.toEqual(body);
  });
});
