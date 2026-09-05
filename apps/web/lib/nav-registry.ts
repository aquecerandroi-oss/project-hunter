/**
 * The single source of the sidebar (docs/ARCHITECTURE.md §8, docs/PRODUCT.md
 * §4). Every route the product will ever have is listed here from M0, with a
 * `status` and the milestone it unlocks at -- an item never renders in
 * production before its milestone (see `visibleNavItems` and CLAUDE.md's "no
 * placeholder / coming soon pages in the nav" rule).
 *
 * Items are PLAIN DATA on purpose: the org layout (a Server Component)
 * computes them and hands them to the client sidebar/mobile nav, and React
 * only lets serialisable values cross that boundary -- no functions, no
 * component references. So the href is a `segment` (resolved by `navHref`)
 * and the icon is a key resolved on the client by `components/layout/nav-icons`.
 */

export type Role = "OWNER" | "ADMIN" | "TRADER" | "ANALYST" | "VIEWER";

const ROLE_RANK: Record<Role, number> = {
  VIEWER: 1,
  ANALYST: 2,
  TRADER: 3,
  ADMIN: 4,
  OWNER: 5,
};

export type NavStatus = "available" | "planned";

export const NAV_ICON_KEYS = [
  "layout-dashboard",
  "radar",
  "line-chart",
  "target",
  "wallet",
  "activity",
  "bot",
  "swords",
  "git-branch",
  "flask-conical",
  "bar-chart-3",
  "brain",
  "shield-alert",
  "building-2",
  "bell",
  "server",
  "settings",
] as const;

export type NavIconKey = (typeof NAV_ICON_KEYS)[number];

export interface NavItem {
  key: string;
  label: string;
  /** Path segment under `/{orgSlug}/`; build the full href with `navHref`. */
  segment: string;
  icon: NavIconKey;
  status: NavStatus;
  /** Milestone or phase this ships in, e.g. "M2" or "Fase 2". Required when planned. */
  plannedMilestone?: string;
  minRole: Role;
}

/** Org-scoped href for an item, e.g. `/acme/dashboard`. */
export function navHref(item: Pick<NavItem, "segment">, orgSlug: string): string {
  return `/${orgSlug}/${item.segment}`;
}

// docs/PRODUCT.md §4 -- table order preserved.
export const NAV_ITEMS: readonly NavItem[] = [
  { key: "dashboard", label: "Dashboard", segment: "dashboard", icon: "layout-dashboard", status: "available", minRole: "VIEWER" },
  { key: "radar", label: "Radar", segment: "radar", icon: "radar", status: "planned", plannedMilestone: "M2", minRole: "VIEWER" },
  { key: "markets", label: "Markets", segment: "markets", icon: "line-chart", status: "available", minRole: "VIEWER" },
  { key: "opportunities", label: "Opportunities", segment: "opportunities", icon: "target", status: "planned", plannedMilestone: "M2", minRole: "VIEWER" },
  { key: "portfolio", label: "Portfolio", segment: "portfolio", icon: "wallet", status: "planned", plannedMilestone: "M3", minRole: "VIEWER" },
  { key: "trades", label: "Trades", segment: "trades", icon: "activity", status: "planned", plannedMilestone: "M3", minRole: "VIEWER" },
  { key: "agents", label: "Agents", segment: "agents", icon: "bot", status: "planned", plannedMilestone: "M4", minRole: "VIEWER" },
  { key: "arena", label: "Agent Arena", segment: "arena", icon: "swords", status: "planned", plannedMilestone: "M6", minRole: "VIEWER" },
  { key: "strategies", label: "Strategies", segment: "strategies", icon: "git-branch", status: "planned", plannedMilestone: "M6", minRole: "VIEWER" },
  { key: "backtests", label: "Backtests", segment: "backtests", icon: "flask-conical", status: "planned", plannedMilestone: "M6", minRole: "VIEWER" },
  { key: "analytics", label: "Analytics", segment: "analytics", icon: "bar-chart-3", status: "planned", plannedMilestone: "M5", minRole: "VIEWER" },
  { key: "intelligence", label: "Intelligence", segment: "intelligence", icon: "brain", status: "planned", plannedMilestone: "Fase 2", minRole: "VIEWER" },
  { key: "risk", label: "Risk Center", segment: "risk", icon: "shield-alert", status: "planned", plannedMilestone: "M4", minRole: "VIEWER" },
  { key: "exchanges", label: "Exchanges", segment: "exchanges", icon: "building-2", status: "planned", plannedMilestone: "Fase 3", minRole: "VIEWER" },
  { key: "alerts", label: "Alerts", segment: "alerts", icon: "bell", status: "planned", plannedMilestone: "Fase 2", minRole: "VIEWER" },
  { key: "system", label: "System", segment: "system", icon: "server", status: "available", minRole: "VIEWER" },
  { key: "settings", label: "Settings", segment: "settings", icon: "settings", status: "available", minRole: "VIEWER" },
];

/**
 * Items a given role/environment combination may see.
 * - `available` items always show (subject to `minRole`).
 * - `planned` items only show outside production, so the team can preview
 *   upcoming nav entries in dev/staging without ever shipping a "coming
 *   soon" page to a real user.
 */
export function visibleNavItems(role: Role, env: string): NavItem[] {
  return NAV_ITEMS.filter((item) => {
    if (ROLE_RANK[role] < ROLE_RANK[item.minRole]) return false;
    if (item.status === "available") return true;
    return env !== "production";
  });
}
