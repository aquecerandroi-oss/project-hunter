"use client";

import { UserButton } from "@clerk/nextjs";
import type { ReactNode } from "react";

import { ThemeToggle } from "@/components/layout/theme-toggle";
import { Separator } from "@/components/ui/separator";

export interface TopbarProps {
  orgSlug: string;
  children?: ReactNode;
}

export function Topbar({ orgSlug, children }: TopbarProps) {
  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-surface-1 px-4">
      {children}
      <span className="truncate text-sm font-medium text-muted">{orgSlug}</span>
      <div className="ml-auto flex items-center gap-2">
        <ThemeToggle />
        <Separator orientation="vertical" className="h-6" />
        <UserButton />
      </div>
    </header>
  );
}
