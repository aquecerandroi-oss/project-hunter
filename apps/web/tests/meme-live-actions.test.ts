import { beforeEach, describe, expect, it, vi } from "vitest";

// `server-only` throws outside Next's real "react-server" build condition.
vi.mock("server-only", () => ({}));

const { apiFetchMock, requireSessionMock } = vi.hoisted(() => ({
  apiFetchMock: vi.fn(),
  requireSessionMock: vi.fn(),
}));

vi.mock("@/lib/server/api", () => ({ apiFetch: apiFetchMock }));
vi.mock("@/lib/server/auth", () => ({ requireSession: requireSessionMock }));

import { sellNowLiveAction } from "@/lib/api/meme-live-actions";

beforeEach(() => {
  apiFetchMock.mockReset();
  requireSessionMock.mockReset().mockResolvedValue({ userId: "u1", token: "t1" });
});

describe("sellNowLiveAction: fails closed, one Idempotency-Key per gesture", () => {
  it("rejects an idempotency key shorter than 8 chars before calling apiFetch", async () => {
    const result = await sellNowLiveAction("org-1", "position-1", "short");
    expect(result.ok).toBe(false);
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("returns the unauthenticated problem without calling apiFetch when there is no session", async () => {
    requireSessionMock.mockResolvedValue(null);
    const result = await sellNowLiveAction("org-1", "position-1", "a".repeat(16));
    expect(result).toEqual({
      ok: false,
      problem: { type: "https://hunter.dev/problems/unauthenticated", title: "Unauthenticated", status: 401, detail: "Sessão não encontrada." },
    });
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("posts to the real position's sell-now with the Idempotency-Key header and an empty body", async () => {
    apiFetchMock.mockResolvedValue({ position_id: "position-1", status: "open", sell_requested_at: "2026-09-12T18:00:00Z", sell_requested_by: "u1", already_requested: false });
    const result = await sellNowLiveAction("org-1", "position-1", "a".repeat(16));
    expect(result.ok).toBe(true);
    const [path, init] = apiFetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/orgs/org-1/meme/live/positions/position-1/sell-now");
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>)["Idempotency-Key"]).toBe("a".repeat(16));
    expect(init.body).toBe("{}");
  });

  it("maps a shape mismatch to a named problem instead of throwing", async () => {
    apiFetchMock.mockResolvedValue({ unexpected: true });
    const result = await sellNowLiveAction("org-1", "position-1", "a".repeat(16));
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.problem.type).toBe("https://hunter.dev/problems/unexpected-response");
  });
});
