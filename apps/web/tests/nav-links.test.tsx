import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/acme/dashboard",
}));

// `@testing-library/react`'s auto-cleanup only self-registers when
// `afterEach` is a real global (vitest's `test.globals` is off in this
// repo), so without this the DOM from each `it` above accumulates and
// later queries see duplicate elements.
afterEach(cleanup);

import { NavLinks } from "@/components/layout/nav-links";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { NavItem } from "@/lib/nav-registry";
import { LayoutDashboard, Radar } from "lucide-react";

const items: NavItem[] = [
  {
    key: "dashboard",
    label: "Dashboard",
    href: (orgSlug: string) => `/${orgSlug}/dashboard`,
    icon: LayoutDashboard,
    status: "available",
    minRole: "VIEWER",
  },
  {
    key: "radar",
    label: "Radar",
    href: (orgSlug: string) => `/${orgSlug}/radar`,
    icon: Radar,
    status: "planned",
    plannedMilestone: "M2",
    minRole: "VIEWER",
  },
];

function renderNav(collapsed = false) {
  return render(
    <TooltipProvider>
      <NavLinks items={items} orgSlug="acme" collapsed={collapsed} />
    </TooltipProvider>,
  );
}

describe("NavLinks planned item accessibility", () => {
  it("renders the planned item as a focusable element in the tab order", () => {
    renderNav();
    const plannedItem = screen.getByRole("button", { name: /radar/i });
    expect(plannedItem).toHaveAttribute("aria-disabled", "true");
    expect(plannedItem).toHaveAttribute("tabIndex", "0");
  });

  it("gives the planned item an accessible description mentioning 'Planejado'", () => {
    renderNav();
    const plannedItem = screen.getByRole("button", { name: /radar/i });
    const describedById = plannedItem.getAttribute("aria-describedby");
    expect(describedById).toBeTruthy();
    const description = document.getElementById(describedById as string);
    expect(description).not.toBeNull();
    expect(description?.textContent).toMatch(/Planejado/);
  });

  it("keeps the accessible description even when the sidebar is collapsed", () => {
    renderNav(true);
    const plannedItem = screen.getByRole("button", { name: /radar/i });
    const describedById = plannedItem.getAttribute("aria-describedby");
    const description = document.getElementById(describedById as string);
    expect(description?.textContent).toMatch(/Planejado/);
  });

  it("does not navigate anywhere when clicked (no href)", () => {
    renderNav();
    const plannedItem = screen.getByRole("button", { name: /radar/i });
    expect(plannedItem).not.toHaveAttribute("href");
  });
});
