import { beforeEach, describe, expect, it, vi } from "vitest";

// `server-only` throws outside Next's real "react-server" build condition.
vi.mock("server-only", () => ({}));

const { apiFetchMock, apiFetchResponseMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn(), apiFetchResponseMock: vi.fn() }));
vi.mock("@/lib/server/api", () => ({ apiFetch: apiFetchMock, apiFetchResponse: apiFetchResponseMock }));

import { ApiError } from "@/lib/api-error";
import { fetchMemeTestsCsv, getMemeTestDetail, getMemeTests, loadMemeTests, memeTestsQuery } from "@/lib/api/meme-tests";

beforeEach(() => {
  apiFetchMock.mockReset().mockResolvedValue({ items: [], real_items: [] });
  apiFetchResponseMock.mockReset().mockResolvedValue(new Response("﻿id;tipo\r\n", { headers: { "content-type": "text/csv; charset=utf-8" } }));
});

describe("getMemeTests: org-scoped read of the day's record", () => {
  it("calls /tests with no query when no params are given", async () => {
    await getMemeTests("org-1");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/v1/orgs/org-1/meme/tests");
  });

  it("serializes day/rule_set/limit/cursor with the API's own names", async () => {
    await getMemeTests("org-1", { day: "2026-09-12", ruleSet: "operator", limit: 200, cursor: "abc" });
    const [path] = apiFetchMock.mock.calls[0] as [string];
    const query = new URLSearchParams(path.split("?")[1]);
    expect(query.get("day")).toBe("2026-09-12");
    expect(query.get("rule_set")).toBe("operator");
    expect(query.get("limit")).toBe("200");
    expect(query.get("cursor")).toBe("abc");
    expect(memeTestsQuery({})).toBe("");
  });

  it("reads one bet's record by id", async () => {
    await getMemeTestDetail("org-1", "bet-1");
    expect(apiFetchMock).toHaveBeenCalledWith("/api/v1/orgs/org-1/meme/tests/bet-1");
  });

  it("asks for the CSV as text/csv through the raw-response client", async () => {
    const response = await fetchMemeTestsCsv("org-1", { day: "2026-09-12" });
    expect(apiFetchResponseMock).toHaveBeenCalledWith("/api/v1/orgs/org-1/meme/tests.csv?day=2026-09-12", "text/csv");
    expect(await response.text()).toContain("id;tipo");
  });

  it("loadMemeTests never throws; the failure is named", async () => {
    apiFetchMock.mockRejectedValueOnce(new ApiError({ type: "about:blank", title: "Bad Gateway", status: 502, detail: "upstream down" }));
    expect(await loadMemeTests("org-1", { day: "2026-09-12" })).toEqual({ ok: false, reason: "upstream down" });
    const ok = await loadMemeTests("org-1");
    expect(ok.ok).toBe(true);
  });
});
