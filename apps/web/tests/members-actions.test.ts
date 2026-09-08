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

import { removeMember, updateMemberRole } from "@/lib/api/members-actions";

beforeEach(() => {
  apiFetchMock.mockReset();
  requireSessionMock.mockReset().mockResolvedValue({ userId: "u1", token: "t1" });
});

/** T3.28c (security-reviewer T3.28a finding 1): same fail-closed guard as `organizations-actions.ts`. */
describe("updateMemberRole: fails closed with no session, never calls apiFetch", () => {
  it("returns the typed unauthenticated problem without calling apiFetch when there is no session", async () => {
    requireSessionMock.mockResolvedValue(null);

    const result = await updateMemberRole("org-1", "u2", "ADMIN");

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

  it("rejects an invalid role before ever checking the session", async () => {
    requireSessionMock.mockResolvedValue(null);

    const result = await updateMemberRole("org-1", "u2", "NOT_A_ROLE");

    expect(result.ok).toBe(false);
    expect(requireSessionMock).not.toHaveBeenCalled();
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("calls apiFetch once a real session is present", async () => {
    apiFetchMock.mockResolvedValue({ user_id: "u2", role: "ADMIN" });

    const result = await updateMemberRole("org-1", "u2", "ADMIN");

    expect(apiFetchMock).toHaveBeenCalledWith(
      "/api/v1/orgs/org-1/members/u2",
      expect.objectContaining({ method: "PATCH" }),
    );
    expect(result.ok).toBe(true);
  });
});

describe("removeMember: fails closed with no session, never calls apiFetch", () => {
  it("returns the typed unauthenticated problem without calling apiFetch when there is no session", async () => {
    requireSessionMock.mockResolvedValue(null);

    const result = await removeMember("org-1", "u2");

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.problem.status).toBe(401);
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("calls apiFetch once a real session is present", async () => {
    apiFetchMock.mockResolvedValue(undefined);

    const result = await removeMember("org-1", "u2");

    expect(apiFetchMock).toHaveBeenCalledWith("/api/v1/orgs/org-1/members/u2", { method: "DELETE" });
    expect(result.ok).toBe(true);
  });
});
