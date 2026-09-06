import { beforeEach, describe, expect, it, vi } from "vitest";

// `server-only` throws when imported outside Next's real "react-server"
// build condition, which Vitest never sets (see tests/invitations-actions.test.ts).
vi.mock("server-only", () => ({}));

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));
vi.mock("@/lib/server/api", () => ({ apiFetch: apiFetchMock }));

import { getLabSignals, getLabSummary, listLabVersions } from "@/lib/api/lab";

beforeEach(() => {
  apiFetchMock.mockReset().mockResolvedValue({ items: [] });
});

describe("listLabVersions: no params, the frozen catalogue endpoint", () => {
  it("calls the versions endpoint with no query string", async () => {
    await listLabVersions();
    expect(apiFetchMock).toHaveBeenCalledWith("/api/v1/lab/shadow/versions");
  });
});

describe("getLabSummary: query building for window/cohort/as_of", () => {
  it("adds no query string when no params are given", async () => {
    await getLabSummary();
    expect(apiFetchMock).toHaveBeenCalledWith("/api/v1/lab/shadow/summary");
  });

  it("serializes window, cohort and as_of together", async () => {
    await getLabSummary({ window: "7d", cohort: "prospective", as_of: "2026-09-06T00:00:00Z" });
    const [path] = apiFetchMock.mock.calls[0] as [string];
    const query = new URLSearchParams(path.split("?")[1]);
    expect(query.get("window")).toBe("7d");
    expect(query.get("cohort")).toBe("prospective");
    expect(query.get("as_of")).toBe("2026-09-06T00:00:00Z");
  });
});

describe("getLabSignals: query building, including `include=envelope`", () => {
  it("adds no query string when no params are given", async () => {
    await getLabSignals();
    expect(apiFetchMock).toHaveBeenCalledWith("/api/v1/lab/shadow/signals");
  });

  it("never sends window/as_of -- this endpoint's contract does not accept them", async () => {
    await getLabSignals({ strategy_version_id: "v1", market: "BTCUSDT" });
    const [path] = apiFetchMock.mock.calls[0] as [string];
    expect(path).not.toContain("window");
    expect(path).not.toContain("as_of");
  });

  it("appends `include=envelope` when requested, alongside the other filters", async () => {
    await getLabSignals({
      strategy_version_id: "v1",
      market: "BTCUSDT",
      cohort: "prospective",
      limit: 200,
      include: ["envelope"],
    });
    const [path] = apiFetchMock.mock.calls[0] as [string];
    const query = new URLSearchParams(path.split("?")[1]);
    expect(query.getAll("include")).toEqual(["envelope"]);
    expect(query.get("strategy_version_id")).toBe("v1");
    expect(query.get("market")).toBe("BTCUSDT");
    expect(query.get("cohort")).toBe("prospective");
    expect(query.get("limit")).toBe("200");
  });

  it("supports cursor pagination", async () => {
    await getLabSignals({ cursor: "abc123" });
    const [path] = apiFetchMock.mock.calls[0] as [string];
    expect(new URLSearchParams(path.split("?")[1]).get("cursor")).toBe("abc123");
  });
});
