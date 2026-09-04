import {
  Activity,
  BarChart3,
  Bell,
  Bot,
  Brain,
  Building2,
  FlaskConical,
  GitBranch,
  LayoutDashboard,
  LineChart,
  type LucideIcon,
  Radar,
  Server,
  Settings,
  ShieldAlert,
  Swords,
  Target,
  Wallet,
} from "lucide-react";

/**
 * The single source of the sidebar (docs/ARCHITECTURE.md §8, docs/PRODUCT.md
 * §4). Every route the product will ever have is listed here from M0, with a
 * `status` and the milestone it unlocks at -- an item never renders in
 * production before its milestone (see `visibleNavItems` and CLAUDE.md's "no
 * placeholder / coming soon pages in the nav" rule).
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

export interface NavItem {
  key: string;
  label: string;
  href: (orgSlug: string) => string;
  icon: LucideIcon;
  status: NavStatus;
  /** Milestone or phase this ships in, e.g. "M2" or "Fase 2". Required when planned. */
  plannedMilestone?: string;
  minRole: Role;
}

function route(segment: string): (orgSlug: string) => string {
  return (orgSlug: string) => `/${orgSlug}/${segment}`;
}

// docs/PRODUCT.md §4 -- table order preserved.
export const NAV_ITEMS: readonly NavItem[] = [
  { key: "dashboard", label: "Dashboard", href: route("dashboard"), icon: LayoutDashboard, status: "available", minRole: "VIEWER" },
  { key: "radar", label: "Radar", href: route("radar"), icon: Radar, status: "planned", plannedMilestone: "M2", minRole: "VIEWER" },
  { key: "markets", label: "Markets", href: route("markets"), icon: LineChart, status: "planned", plannedMilestone: "M1", minRole: "VIEWER" },
  { key: "opportunities", label: "Opportunities", href: route("opportunities"), icon: Target, status: "planned", plannedMilestone: "M2", minRole: "VIEWER" },
  { key: "portfolio", label: "Portfolio", href: route("portfolio"), icon: Wallet, status: "planned", plannedMilestone: "M3", minRole: "VIEWER" },
  { key: "trades", label: "Trades", href: route("trades"), icon: Activity, status: "planned", plannedMilestone: "M3", minRole: "VIEWER" },
  { key: "agents", label: "Agents", href: route("agents"), icon: Bot, status: "planned", plannedMilestone: "M4", minRole: "VIEWER" },
  { key: "arena", label: "Agent Arena", href: route("arena"), icon: Swords, status: "planned", plannedMilestone: "M6", minRole: "VIEWER" },
  { key: "strategies", label: "Strategies", href: route("strategies"), icon: GitBranch, status: "planned", plannedMilestone: "M6", minRole: "VIEWER" },
  { key: "backtests", label: "Backtests", href: route("backtests"), icon: FlaskConical, status: "planned", plannedMilestone: "M6", minRole: "VIEWER" },
  { key: "analytics", label: "Analytics", href: route("analytics"), icon: BarChart3, status: "planned", plannedMilestone: "M5", minRole: "VIEWER" },
  { key: "intelligence", label: "Intelligence", href: route("intelligence"), icon: Brain, status: "planned", plannedMilestone: "Fase 2", minRole: "VIEWER" },
  { key: "risk", label: "Risk Center", href: route("risk"), icon: ShieldAlert, status: "planned", plannedMilestone: "M4", minRole: "VIEWER" },
  { key: "exchanges", label: "Exchanges", href: route("exchanges"), icon: Building2, status: "planned", plannedMilestone: "Fase 3", minRole: "VIEWER" },
  { key: "alerts", label: "Alerts", href: route("alerts"), icon: Bell, status: "planned", plannedMilestone: "Fase 2", minRole: "VIEWER" },
  { key: "system", label: "System", href: route("system"), icon: Server, status: "available", minRole: "VIEWER" },
  { key: "settings", label: "Settings", href: route("settings"), icon: Settings, status: "available", minRole: "VIEWER" },
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
