import { describe, expect, it } from "vitest";

import { buildLabHref } from "@/components/lab/lab-signals-query";

const base = { window: "30d", cohort: "prospective", versionId: undefined, state: "closed" as const, pageSize: 200 as const, cursorPath: [] };

describe("buildLabHref: the query string every tab/pager click navigates to (brief T3.37)", () => {
  it("always sets window/state/page_size, omitting cohort when it is the endpoint's own default", () => {
    const href = buildLabHref("/acme/lab", base);
    expect(href).toBe("/acme/lab?window=30d&state=closed&page_size=200");
  });

  it("includes cohort when it is not 'prospective'", () => {
    const href = buildLabHref("/acme/lab", { ...base, cohort: "replay:11111111-1111-1111-1111-111111111111" });
    const query = new URLSearchParams(href.split("?")[1]);
    expect(query.get("cohort")).toBe("replay:11111111-1111-1111-1111-111111111111");
  });

  it("includes version only when set", () => {
    const withVersion = new URLSearchParams(buildLabHref("/acme/lab", { ...base, versionId: "v1" }).split("?")[1]);
    expect(withVersion.get("version")).toBe("v1");
    const withoutVersion = new URLSearchParams(buildLabHref("/acme/lab", base).split("?")[1]);
    expect(withoutVersion.has("version")).toBe(false);
  });

  it("appends every cursor in cursorPath as its own repeated 'c' param, in order", () => {
    const href = buildLabHref("/acme/lab", { ...base, cursorPath: ["cursor-1", "cursor-2"] });
    const query = new URLSearchParams(href.split("?")[1]);
    expect(query.getAll("c")).toEqual(["cursor-1", "cursor-2"]);
  });

  it("omits 'c' entirely for page 1 (an empty cursorPath)", () => {
    const href = buildLabHref("/acme/lab", base);
    expect(href).not.toContain("c=");
  });

  it("reflects the target state, not the current one -- callers always pass the state they want to navigate to", () => {
    const href = buildLabHref("/acme/lab", { ...base, state: "open" });
    expect(new URLSearchParams(href.split("?")[1]).get("state")).toBe("open");
  });
});
