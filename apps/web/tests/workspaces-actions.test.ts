import { beforeEach, describe, expect, it, vi } from "vitest";

// `server-only` throws when imported outside Next's real "react-server"
// build condition, which Vitest never sets (see tests/invitations-actions.test.ts).
vi.mock("server-only", () => ({}));

const { apiFetchMock, requireSessionMock } = vi.hoisted(() => ({
  apiFetchMock: vi.fn(),
  requireSessionMock: vi.fn(),
}));

vi.mock("@/lib/server/api", () => ({
  apiFetch: apiFetchMock,
}));

vi.mock("@/lib/server/auth", () => ({
  requireSession: requireSessionMock,
}));

import { putOnboarding } from "@/lib/api/workspaces-actions";

const VALID_INPUT = {
  objective: "explore",
  virtualCapital: "10000",
  riskPreset: "balanced",
  monitoredExchanges: ["binance"],
};

beforeEach(() => {
  apiFetchMock.mockReset();
  requireSessionMock.mockReset().mockResolvedValue({ userId: "u1", token: "t1" });
});

/** T3.28c (security-reviewer T3.28a finding 1): same fail-closed guard as `organizations-actions.ts`. */
describe("putOnboarding: fails closed with no session, never calls apiFetch", () => {
  it("returns the typed unauthenticated problem without calling apiFetch when there is no session", async () => {
    requireSessionMock.mockResolvedValue(null);

    const result = await putOnboarding("org-1", "ws-1", VALID_INPUT);

    expect(result).toEqual({
      ok: false,
      problem: {
        type: "https://hunter.dev/problems/unauthenticated",
        title: "Unauthenticated",
        status: 401,
        detail: "Sessão não encontrada.",
      },
    });
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("rejects invalid input before ever checking the session", async () => {
    requireSessionMock.mockResolvedValue(null);

    const result = await putOnboarding("org-1", "ws-1", { ...VALID_INPUT, virtualCapital: "1" });

    expect(result.ok).toBe(false);
    expect(requireSessionMock).not.toHaveBeenCalled();
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("calls apiFetch once a real session is present", async () => {
    apiFetchMock.mockResolvedValue({ id: "ws-1", name: "Main" });

    const result = await putOnboarding("org-1", "ws-1", VALID_INPUT);

    expect(apiFetchMock).toHaveBeenCalledWith(
      "/api/v1/orgs/org-1/workspaces/ws-1/onboarding",
      expect.objectContaining({ method: "PUT" }),
    );
    expect(result.ok).toBe(true);
  });
});
