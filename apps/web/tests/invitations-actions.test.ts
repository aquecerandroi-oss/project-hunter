import { beforeEach, describe, expect, it, vi } from "vitest";

// `server-only` throws when imported outside Next's real "react-server"
// build condition, which Vitest never sets -- every module this file
// imports (`lib/api/types.ts`, `lib/server/api.ts`, `lib/api/organizations.ts`)
// carries that guard. Neutralizing the marker package itself is simpler and
// more robust than mocking each of those individually as this action's own
// dependency graph grows.
vi.mock("server-only", () => ({}));

const { apiFetchMock, getOrganizationMock } = vi.hoisted(() => ({
  apiFetchMock: vi.fn(),
  getOrganizationMock: vi.fn(),
}));

vi.mock("@/lib/server/api", () => ({
  apiFetch: apiFetchMock,
}));

vi.mock("@/lib/api/organizations", () => ({
  getOrganization: getOrganizationMock,
}));

import { ApiError } from "@/lib/api-error";
import { acceptInvitation } from "@/lib/api/invitations-actions";

const VALID_TOKEN = "a".repeat(32);

beforeEach(() => {
  apiFetchMock.mockReset();
  getOrganizationMock.mockReset();
});

describe("acceptInvitation: token shape validation (zod, before ever calling the API)", () => {
  it("rejects a token shorter than 32 characters without calling apiFetch", async () => {
    const result = await acceptInvitation("short");
    expect(result.ok).toBe(false);
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("rejects a token with characters outside the url-safe alphabet", async () => {
    const result = await acceptInvitation(`${VALID_TOKEN.slice(0, 31)}!`);
    expect(result.ok).toBe(false);
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("rejects a token longer than 128 characters", async () => {
    const result = await acceptInvitation("a".repeat(129));
    expect(result.ok).toBe(false);
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("accepts a 32-char url-safe token shape and calls the accept endpoint", async () => {
    apiFetchMock.mockResolvedValue({ organization_id: "org-1", user_id: "u1", role: "VIEWER" });
    getOrganizationMock.mockResolvedValue({ id: "org-1", slug: "acme" });

    const result = await acceptInvitation(VALID_TOKEN);

    expect(apiFetchMock).toHaveBeenCalledWith(`/api/v1/invitations/${VALID_TOKEN}/accept`, { method: "POST" });
    expect(getOrganizationMock).toHaveBeenCalledWith("org-1");
    expect(result).toEqual({ ok: true, data: { orgSlug: "acme" } });
  });
});

describe("acceptInvitation: error mapping (routers/invitations.py's accept endpoint)", () => {
  it("maps a 404 to the generic 'invalid/expired/used' message, not the raw API detail", async () => {
    apiFetchMock.mockRejectedValue(
      new ApiError({
        type: "https://hunter.dev/problems/invitation-not-found",
        title: "Not Found",
        status: 404,
        detail: "This invitation link is not valid or has expired.",
      }),
    );

    const result = await acceptInvitation(VALID_TOKEN);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.problem.status).toBe(404);
      expect(result.problem.detail).toMatch(/inválido, expirado ou já usado/i);
      expect(result.problem.detail).not.toMatch(/valid or has expired/i);
    }
  });

  it("passes through the API's own detail on a 403 (email mismatch)", async () => {
    apiFetchMock.mockRejectedValue(
      new ApiError({
        type: "https://hunter.dev/problems/invitation-email-mismatch",
        title: "Forbidden",
        status: 403,
        detail: "This invitation was issued to a different email address.",
      }),
    );

    const result = await acceptInvitation(VALID_TOKEN);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.problem.status).toBe(403);
      expect(result.problem.detail).toBe("This invitation was issued to a different email address.");
    }
  });
});
