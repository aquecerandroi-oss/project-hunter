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

import type { NavIconKey } from "@/lib/nav-registry";

/**
 * Client-side resolution of the nav registry's icon keys. Lives apart from
 * `lib/nav-registry.ts` so the registry stays plain, serialisable data that a
 * Server Component can pass to the sidebar (React forbids component
 * references across that boundary).
 */
export const NAV_ICONS: Record<NavIconKey, LucideIcon> = {
  "layout-dashboard": LayoutDashboard,
  radar: Radar,
  "line-chart": LineChart,
  target: Target,
  wallet: Wallet,
  activity: Activity,
  bot: Bot,
  swords: Swords,
  "git-branch": GitBranch,
  "flask-conical": FlaskConical,
  "bar-chart-3": BarChart3,
  brain: Brain,
  "shield-alert": ShieldAlert,
  "building-2": Building2,
  bell: Bell,
  server: Server,
  settings: Settings,
};
