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

import { createOrganization, updateOrganization } from "@/lib/api/organizations-actions";

beforeEach(() => {
  apiFetchMock.mockReset();
  requireSessionMock.mockReset().mockResolvedValue({ userId: "u1", token: "t1" });
});

/**
 * T3.28c (security-reviewer T3.28a finding 1): `/` is public in
 * `middleware.ts`, so an unauthenticated POST carrying a `Next-Action` id
 * still reaches these actions. Before this fix, `apiFetch` issued the
 * outbound request regardless (the API answered 401, but the request had
 * already spent the web peer's shared rate-limit bucket). Every case below
 * asserts `apiFetch` is never called without a session.
 */
describe("createOrganization: fails closed with no session, never calls apiFetch", () => {
  it("returns the typed unauthenticated problem without calling apiFetch when there is no session", async () => {
    requireSessionMock.mockResolvedValue(null);

    const result = await createOrganization({ name: "Acme" });

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

    const result = await createOrganization({ name: "" });

    expect(result.ok).toBe(false);
    expect(requireSessionMock).not.toHaveBeenCalled();
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("calls apiFetch once a real session is present", async () => {
    apiFetchMock.mockResolvedValue({ id: "org-1", slug: "acme", name: "Acme" });

    const result = await createOrganization({ name: "Acme" });

    expect(apiFetchMock).toHaveBeenCalledWith(
      "/api/v1/orgs",
      expect.objectContaining({ method: "POST" }),
    );
    expect(result).toEqual({ ok: true, data: { id: "org-1", slug: "acme", name: "Acme" } });
  });
});

describe("updateOrganization: fails closed with no session, never calls apiFetch", () => {
  it("returns the typed unauthenticated problem without calling apiFetch when there is no session", async () => {
    requireSessionMock.mockResolvedValue(null);

    const result = await updateOrganization("org-1", "Nova Acme");

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.problem.status).toBe(401);
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("calls apiFetch once a real session is present", async () => {
    apiFetchMock.mockResolvedValue({ id: "org-1", slug: "acme", name: "Nova Acme" });

    const result = await updateOrganization("org-1", "Nova Acme");

    expect(apiFetchMock).toHaveBeenCalledWith(
      "/api/v1/orgs/org-1",
      expect.objectContaining({ method: "PATCH" }),
    );
    expect(result.ok).toBe(true);
  });
});
