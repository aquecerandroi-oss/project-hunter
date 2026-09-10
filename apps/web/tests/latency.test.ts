import { beforeEach, describe, expect, it, vi } from "vitest";

// `server-only` throws when imported outside Next's real "react-server"
// build condition, which Vitest never sets (see tests/invitations-actions.test.ts).
vi.mock("server-only", () => ({}));

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));
vi.mock("@/lib/server/api", () => ({ apiFetch: apiFetchMock }));

import { getLatency } from "@/lib/api/latency";

const VALID = {
  hops: [{ hop: "ingest", p50_s: 0.09, p95_s: 0.31, target_p50_s: 0.5, target_p95_s: 1.0, status: "ok" }],
  end_to_end: { hop: "end_to_end", p50_s: null, p95_s: null, target_p50_s: 5.0, target_p95_s: 10.0, status: "unknown" },
  generated_at: "2026-09-10T16:24:00Z",
};

beforeEach(() => {
  apiFetchMock.mockReset();
});

describe("getLatency: GET /api/v1/system/latency, parsed before this app trusts it", () => {
  it("calls the right path and returns the parsed body", async () => {
    apiFetchMock.mockResolvedValue(VALID);

    const result = await getLatency();

    expect(apiFetchMock).toHaveBeenCalledWith("/api/v1/system/latency");
    expect(result.generated_at).toBe("2026-09-10T16:24:00Z");
    expect(result.hops[0]?.status).toBe("ok");
  });

  it("throws instead of silently returning a shape drift from the API", async () => {
    apiFetchMock.mockResolvedValue({ hops: [], end_to_end: null, generated_at: "x" });

    await expect(getLatency()).rejects.toThrow();
  });
});
