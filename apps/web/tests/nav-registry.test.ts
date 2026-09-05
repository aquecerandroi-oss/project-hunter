import { describe, expect, it } from "vitest";

import { NAV_ICONS } from "@/components/layout/nav-icons";
import { NAV_ICON_KEYS, NAV_ITEMS, navHref, visibleNavItems } from "@/lib/nav-registry";

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
    expect(dashboard ? navHref(dashboard, "acme") : null).toBe("/acme/dashboard");
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

describe("nav-registry crosses the server -> client boundary", () => {
  it("every item is plain, serialisable data (no functions, no component refs)", () => {
    // The org layout (Server Component) passes these to the client sidebar;
    // React throws "Only plain objects can be passed to Client Components"
    // for anything that does not survive a JSON round-trip.
    for (const item of NAV_ITEMS) {
      expect(JSON.parse(JSON.stringify(item))).toEqual(item);
      for (const value of Object.values(item)) expect(typeof value).not.toBe("function");
    }
  });

  it("every icon key resolves to a client-side icon component", () => {
    for (const item of NAV_ITEMS) {
      expect(NAV_ICON_KEYS).toContain(item.icon);
      expect(NAV_ICONS[item.icon], `${item.key}: icon "${item.icon}" has no component`).toBeDefined();
    }
  });
});
