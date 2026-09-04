"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

export interface SettingsNavProps {
  orgSlug: string;
}

/** Settings sub-nav (docs/PRODUCT.md §4: profile, organization, members, security, appearance -- all M0). */
const TABS = [
  { key: "profile", label: "Perfil" },
  { key: "organization", label: "Organização" },
  { key: "members", label: "Membros" },
  { key: "security", label: "Segurança" },
  { key: "appearance", label: "Aparência" },
] as const;

export function SettingsNav({ orgSlug }: SettingsNavProps) {
  const pathname = usePathname();

  return (
    <nav className="flex gap-1 overflow-x-auto border-b border-border pb-2" aria-label="Navegação de configurações">
      {TABS.map((tab) => {
        const href = `/${orgSlug}/settings/${tab.key}`;
        const isActive = pathname === href;
        return (
          <Link
            key={tab.key}
            href={href}
            aria-current={isActive ? "page" : undefined}
            className={cn(
              "shrink-0 rounded-md px-3 py-1.5 text-sm font-medium text-foreground/80 hover:bg-surface-2 hover:text-foreground",
              isActive && "bg-surface-2 text-foreground",
            )}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
