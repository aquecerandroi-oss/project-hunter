"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { PlannedBadge } from "@/components/layout/planned-badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { NAV_ICONS } from "@/components/layout/nav-icons";
import { type NavItem, navHref } from "@/lib/nav-registry";
import { cn } from "@/lib/utils";

export interface NavLinksProps {
  items: NavItem[];
  orgSlug: string;
  collapsed?: boolean;
  onNavigate?: () => void;
}

/** Shared between the desktop sidebar and the mobile sheet so both render the exact same nav-registry output. */
export function NavLinks({ items, orgSlug, collapsed = false, onNavigate = () => {} }: NavLinksProps) {
  const pathname = usePathname();

  return (
    <nav className="flex flex-col gap-1" aria-label="Navegação principal">
      {items.map((item) => {
        const Icon = NAV_ICONS[item.icon];
        const label = <span className={cn("truncate", collapsed && "sr-only")}>{item.label}</span>;

        if (item.status === "planned") {
          const descriptionId = `nav-planned-desc-${item.key}`;
          return (
            <Tooltip key={item.key}>
              <TooltipTrigger asChild>
                {/*
                 * A real, focusable <button> (not a <span>) so keyboard users
                 * tab onto it like any other nav item. `aria-disabled` (not
                 * the `disabled` attribute) keeps it in the tab order while
                 * announcing the disabled state; the click handler is a
                 * no-op guard since there is no href to navigate to anyway.
                 * `aria-describedby` points at a visually-hidden description
                 * so the "Planejado" reason reaches screen-reader users even
                 * when the sidebar is collapsed and the label itself is
                 * `sr-only`.
                 */}
                <button
                  type="button"
                  aria-disabled="true"
                  aria-describedby={descriptionId}
                  tabIndex={0}
                  onClick={(event) => event.preventDefault()}
                  className="flex w-full cursor-not-allowed items-center gap-2 rounded-md border-l-2 border-transparent px-3 py-2 text-left text-sm text-fg-subtle opacity-60"
                >
                  <Icon className="size-4 shrink-0" aria-hidden="true" />
                  {label}
                  {!collapsed && <PlannedBadge milestone={item.plannedMilestone ?? "?"} className="ml-auto" />}
                  <span id={descriptionId} className="sr-only">
                    Planejado para {item.plannedMilestone ?? "uma versão futura"}. Disponível a partir de{" "}
                    {item.plannedMilestone}.
                  </span>
                </button>
              </TooltipTrigger>
              <TooltipContent side={collapsed ? "right" : "top"}>
                Disponível a partir de {item.plannedMilestone}
              </TooltipContent>
            </Tooltip>
          );
        }

        const href = navHref(item, orgSlug);
        const isActive = pathname === href;

        return (
          <Link
            key={item.key}
            href={href}
            onClick={onNavigate}
            aria-current={isActive ? "page" : undefined}
            className={cn(
              // 2px transparent border reserves the space the gold active
              // bar occupies so the label doesn't shift when it appears
              // (docs/DESIGN.md §3: "item ativo com barra dourada de 2px").
              "flex items-center gap-2 rounded-md border-l-2 border-transparent px-3 py-2 text-sm font-medium text-fg/80 hover:bg-bg-overlay hover:text-fg",
              isActive && "border-gold bg-bg-overlay text-fg",
            )}
          >
            <Icon className="size-4 shrink-0" aria-hidden="true" />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
