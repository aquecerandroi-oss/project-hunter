"use client";

import { ChevronsLeft, ChevronsRight } from "lucide-react";
import { useState } from "react";

import { NavLinks } from "@/components/layout/nav-links";
import { Button } from "@/components/ui/button";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { NavItem } from "@/lib/nav-registry";
import { cn } from "@/lib/utils";

export interface SidebarProps {
  items: NavItem[];
  orgSlug: string;
  className?: string;
}

export function Sidebar({ items, orgSlug, className }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <TooltipProvider delayDuration={200}>
      <aside
        className={cn(
          "flex shrink-0 flex-col border-r border-border bg-surface-1 transition-[width] duration-150",
          collapsed ? "w-16" : "w-60",
          className,
        )}
      >
        <div className="flex h-14 shrink-0 items-center justify-between px-3">
          {!collapsed && <span className="truncate text-sm font-semibold">Hunter</span>}
          <Button
            variant="ghost"
            size="icon"
            aria-label={collapsed ? "Expandir menu" : "Recolher menu"}
            aria-expanded={!collapsed}
            onClick={() => setCollapsed((value) => !value)}
          >
            {collapsed ? <ChevronsRight className="size-4" /> : <ChevronsLeft className="size-4" />}
          </Button>
        </div>
        <div className={cn("flex-1 overflow-y-auto px-2 pb-4", collapsed && "px-1")}>
          <NavLinks items={items} orgSlug={orgSlug} collapsed={collapsed} />
        </div>
      </aside>
    </TooltipProvider>
  );
}
