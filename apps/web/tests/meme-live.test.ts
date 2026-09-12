import { describe, expect, it, vi } from "vitest";

// `server-only` throws outside Next's real "react-server" build condition.
vi.mock("server-only", () => ({}));

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));
vi.mock("@/lib/server/api", () => ({ apiFetch: apiFetchMock }));

import { getMemeLive } from "@/lib/api/meme-live";

describe("getMemeLive: org-scoped read of the real executor", () => {
  it("calls GET /meme/live for the org", async () => {
    apiFetchMock.mockReset().mockResolvedValue({ label: "REAL", api_live_enabled: false });
    await getMemeLive("org-1");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/v1/orgs/org-1/meme/live");
  });
});
