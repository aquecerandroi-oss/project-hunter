import { beforeEach, describe, expect, it, vi } from "vitest";

// `server-only` throws when imported outside Next's real "react-server"
// build condition, which Vitest never sets (see tests/organizations-actions.test.ts).
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

import { fileManualOrderAction, pollManualOrderAction } from "@/lib/api/manual-orders-actions";

const VALID_INPUT = {
  market_id: "3f6b3b9a-6b1a-4e6a-9c1a-000000000001",
  direction: "long" as const,
  stop: "63700.00",
  requested_notional: null,
};

beforeEach(() => {
  apiFetchMock.mockReset();
  requireSessionMock.mockReset().mockResolvedValue({ userId: "u1", token: "t1" });
});

describe("fileManualOrderAction: fails closed, never calls apiFetch without a valid session or shape", () => {
  it("rejects invalid input (bad market_id) before ever checking the session", async () => {
    const result = await fileManualOrderAction("org-1", "wallet-1", "a".repeat(16), { ...VALID_INPUT, market_id: "not-a-uuid" });

    expect(result.ok).toBe(false);
    expect(requireSessionMock).not.toHaveBeenCalled();
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("rejects an idempotency key shorter than 8 chars before calling apiFetch", async () => {
    const result = await fileManualOrderAction("org-1", "wallet-1", "short", VALID_INPUT);

    expect(result.ok).toBe(false);
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("returns the unauthenticated problem without calling apiFetch when there is no session", async () => {
    requireSessionMock.mockResolvedValue(null);

    const result = await fileManualOrderAction("org-1", "wallet-1", "a".repeat(16), VALID_INPUT);

    expect(result).toEqual({
      ok: false,
      problem: { type: "https://hunter.dev/problems/unauthenticated", title: "Unauthenticated", status: 401, detail: "Sessão não encontrada." },
    });
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("POSTs to the org-scoped order-requests path with the Idempotency-Key header and the exact body", async () => {
    const key = "a".repeat(16);
    apiFetchMock.mockResolvedValue({
      request_id: "req-1",
      market_id: VALID_INPUT.market_id,
      direction: "long",
      status: "pending",
      filed_at: "2026-09-10T12:00:00Z",
      decision: null,
    });

    const result = await fileManualOrderAction("org-1", "wallet-1", key, VALID_INPUT);

    expect(apiFetchMock).toHaveBeenCalledWith(
      "/api/v1/orgs/org-1/portfolios/wallet-1/order-requests",
      expect.objectContaining({
        method: "POST",
        headers: { "Idempotency-Key": key },
        body: JSON.stringify(VALID_INPUT),
      }),
    );
    expect(result).toEqual({
      ok: true,
      data: { request_id: "req-1", market_id: VALID_INPUT.market_id, direction: "long", status: "pending", filed_at: "2026-09-10T12:00:00Z", decision: null },
    });
  });

  it("propagates a 409 (idempotency-key-conflict/wallet-not-open) as a typed problem, not a throw", async () => {
    // `problemFromApiError` narrows via `instanceof ApiError` (the real
    // class from `lib/api-error.ts`), so this constructs a real one rather
    // than a lookalike. Slug matches `services/admission.py::OrderReplayConflictError`.
    const { ApiError } = await import("@/lib/api-error");
    const realError = new ApiError({
      type: "https://hunter.dev/problems/idempotency-key-conflict",
      title: "Conflict",
      status: 409,
      detail: "Different order under the same key.",
    });
    apiFetchMock.mockRejectedValue(realError);

    const result = await fileManualOrderAction("org-1", "wallet-1", "a".repeat(16), VALID_INPUT);

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.problem.status).toBe(409);
      expect(result.problem.type).toBe("https://hunter.dev/problems/idempotency-key-conflict");
    }
  });

  it("returns an honest 'unexpected response' problem when the API answers with a shape this app does not recognize", async () => {
    apiFetchMock.mockResolvedValue({ nonsense: true });

    const result = await fileManualOrderAction("org-1", "wallet-1", "a".repeat(16), VALID_INPUT);

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.problem.status).toBe(502);
  });
});

describe("pollManualOrderAction", () => {
  it("fails closed without a session", async () => {
    requireSessionMock.mockResolvedValue(null);

    const result = await pollManualOrderAction("org-1", "wallet-1", "req-1");

    expect(result.ok).toBe(false);
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("GETs the single-request path and parses a decided response", async () => {
    apiFetchMock.mockResolvedValue({
      request_id: "req-1",
      market_id: VALID_INPUT.market_id,
      direction: "long",
      status: "decided",
      filed_at: "2026-09-10T12:00:00Z",
      decision: null,
      outcome: null,
    });

    const result = await pollManualOrderAction("org-1", "wallet-1", "req-1");

    expect(apiFetchMock).toHaveBeenCalledWith("/api/v1/orgs/org-1/portfolios/wallet-1/order-requests/req-1");
    expect(result).toEqual({
      ok: true,
      data: { request_id: "req-1", market_id: VALID_INPUT.market_id, direction: "long", status: "decided", filed_at: "2026-09-10T12:00:00Z", decision: null, outcome: null },
    });
  });
});
