import { beforeEach, describe, expect, it, vi } from "vitest";

// `server-only` throws when imported outside Next's real "react-server"
// build condition, which Vitest never sets (see tests/invitations-actions.test.ts).
vi.mock("server-only", () => ({}));

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));
vi.mock("@/lib/server/api", () => ({ apiFetch: apiFetchMock }));

import { getMemeOverview, getMemeToken, listMemeGaps, listMemeTokens } from "@/lib/api/meme";

beforeEach(() => {
  apiFetchMock.mockReset().mockResolvedValue({ items: [] });
});

describe("getMemeOverview: org-scoped, no params", () => {
  it("calls the overview endpoint under the org path", async () => {
    await getMemeOverview("org-1");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/v1/orgs/org-1/meme/overview");
  });
});

describe("listMemeTokens: query building for state/sort/limit/cursor", () => {
  it("adds no query string when no params are given", async () => {
    await listMemeTokens("org-1");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/v1/orgs/org-1/meme/tokens");
  });

  it("serializes every param together", async () => {
    await listMemeTokens("org-1", { state: "curve", sort: "progress", limit: 50, cursor: "abc" });
    const [path] = apiFetchMock.mock.calls[0] as [string];
    expect(path.startsWith("/api/v1/orgs/org-1/meme/tokens?")).toBe(true);
    const query = new URLSearchParams(path.split("?")[1]);
    expect(query.get("state")).toBe("curve");
    expect(query.get("sort")).toBe("progress");
    expect(query.get("limit")).toBe("50");
    expect(query.get("cursor")).toBe("abc");
  });
});

describe("getMemeToken: mint is URL-encoded, snapshot/feature limits are optional", () => {
  it("encodes the mint into the path", async () => {
    await getMemeToken("org-1", "Mint/With/Slash");
    const [path] = apiFetchMock.mock.calls[0] as [string];
    expect(path).toBe("/api/v1/orgs/org-1/meme/tokens/Mint%2FWith%2FSlash");
  });

  it("adds snapshot_limit/feature_limit as query params when given", async () => {
    await getMemeToken("org-1", "MintABC", { snapshot_limit: 100, feature_limit: 200 });
    const [path] = apiFetchMock.mock.calls[0] as [string];
    const query = new URLSearchParams(path.split("?")[1]);
    expect(query.get("snapshot_limit")).toBe("100");
    expect(query.get("feature_limit")).toBe("200");
  });
});

describe("listMemeGaps: cursor pagination, no state/sort", () => {
  it("adds no query string when no params are given", async () => {
    await listMemeGaps("org-1");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/v1/orgs/org-1/meme/gaps");
  });

  it("serializes limit and cursor", async () => {
    await listMemeGaps("org-1", { limit: 20, cursor: "xyz" });
    const [path] = apiFetchMock.mock.calls[0] as [string];
    const query = new URLSearchParams(path.split("?")[1]);
    expect(query.get("limit")).toBe("20");
    expect(query.get("cursor")).toBe("xyz");
  });
});
