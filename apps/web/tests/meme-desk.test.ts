import { beforeEach, describe, expect, it, vi } from "vitest";

// `server-only` throws outside Next's real "react-server" build condition.
vi.mock("server-only", () => ({}));

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));
vi.mock("@/lib/server/api", () => ({ apiFetch: apiFetchMock }));

import { ApiError } from "@/lib/api-error";
import { getMemeDesk, getMemeLoopState } from "@/lib/api/meme-desk";

beforeEach(() => {
  apiFetchMock.mockReset().mockResolvedValue({ items: [] });
});

describe("getMemeDesk: org-scoped desk read", () => {
  it("calls /desk with no query when no params are given", async () => {
    await getMemeDesk("org-1");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/v1/orgs/org-1/meme/desk");
  });

  it("serializes status/limit/cursor", async () => {
    await getMemeDesk("org-1", { status: "proposed", limit: 200, cursor: "abc" });
    const [path] = apiFetchMock.mock.calls[0] as [string];
    const query = new URLSearchParams(path.split("?")[1]);
    expect(query.get("status")).toBe("proposed");
    expect(query.get("limit")).toBe("200");
    expect(query.get("cursor")).toBe("abc");
  });
});

describe("getMemeLoopState: reads GET /meme/lab defensively (T4.6 may not exist yet)", () => {
  it("returns the tick when the placar carries sources.lab_last_tick_at", async () => {
    apiFetchMock.mockResolvedValueOnce({ sources: { lab_last_tick_at: "2026-09-12T12:00:00Z" } });
    expect(await getMemeLoopState("org-1")).toEqual({ lastTickAt: "2026-09-12T12:00:00Z", reason: null });
    expect(apiFetchMock).toHaveBeenCalledWith("/api/v1/orgs/org-1/meme/lab");
  });

  it("a null tick is a reading (the loop never ran), not a missing endpoint", async () => {
    apiFetchMock.mockResolvedValueOnce({ sources: { lab_last_tick_at: null } });
    expect(await getMemeLoopState("org-1")).toEqual({ lastTickAt: null, reason: null });
  });

  it("names endpoint_missing on a 404 instead of throwing", async () => {
    apiFetchMock.mockRejectedValueOnce(new ApiError({ type: "about:blank", title: "Not Found", status: 404 }));
    expect(await getMemeLoopState("org-1")).toEqual({ lastTickAt: null, reason: "endpoint_missing" });
  });

  it("names read_failed on any other failure", async () => {
    apiFetchMock.mockRejectedValueOnce(new ApiError({ type: "about:blank", title: "Bad Gateway", status: 502 }));
    expect(await getMemeLoopState("org-1")).toEqual({ lastTickAt: null, reason: "read_failed" });
  });

  it("names shape_unknown when the payload has no tick field", async () => {
    apiFetchMock.mockResolvedValueOnce({ scoreboard: [] });
    expect(await getMemeLoopState("org-1")).toEqual({ lastTickAt: null, reason: "shape_unknown" });
  });
});
