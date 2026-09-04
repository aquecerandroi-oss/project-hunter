import { describe, expect, it } from "vitest";

import { NAV_ITEMS, visibleNavItems } from "@/lib/nav-registry";

describe("nav-registry", () => {
  it("lists all 17 routes from docs/PRODUCT.md §4", () => {
    expect(NAV_ITEMS).toHaveLength(17);
    const keys = NAV_ITEMS.map((item) => item.key);
    expect(new Set(keys).size).toBe(17);
  });

  it("marks only dashboard, system and settings available in M0", () => {
    const available = NAV_ITEMS.filter((item) => item.status === "available").map((item) => item.key);
    expect(available.sort()).toEqual(["dashboard", "settings", "system"]);
  });

  it("gives every planned item a milestone", () => {
    for (const item of NAV_ITEMS) {
      if (item.status === "planned") {
        expect(item.plannedMilestone, `${item.key} is planned but has no milestone`).toBeTruthy();
      }
    }
  });

  it("builds an org-scoped href", () => {
    const dashboard = NAV_ITEMS.find((item) => item.key === "dashboard");
    expect(dashboard?.href("acme")).toBe("/acme/dashboard");
  });

  it("hides planned items in production", () => {
    const items = visibleNavItems("OWNER", "production");
    expect(items.every((item) => item.status === "available")).toBe(true);
    expect(items.map((item) => item.key).sort()).toEqual(["dashboard", "settings", "system"]);
  });

  it("shows planned items outside production", () => {
    const items = visibleNavItems("OWNER", "development");
    expect(items).toHaveLength(17);
    const radar = items.find((item) => item.key === "radar");
    expect(radar?.status).toBe("planned");
  });

  it("never hides an available item regardless of role", () => {
    for (const role of ["OWNER", "ADMIN", "TRADER", "ANALYST", "VIEWER"] as const) {
      const items = visibleNavItems(role, "production");
      expect(items.map((item) => item.key).sort()).toEqual(["dashboard", "settings", "system"]);
    }
  });
});
