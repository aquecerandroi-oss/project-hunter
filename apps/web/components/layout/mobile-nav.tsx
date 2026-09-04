"use client";

import { Menu } from "lucide-react";
import { useState } from "react";

import { NavLinks } from "@/components/layout/nav-links";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { NavItem } from "@/lib/nav-registry";

export interface MobileNavProps {
  items: NavItem[];
  orgSlug: string;
}

export function MobileNav({ items, orgSlug }: MobileNavProps) {
  const [open, setOpen] = useState(false);

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" className="md:hidden" aria-label="Abrir navegação">
          <Menu className="size-5" />
        </Button>
      </SheetTrigger>
      <SheetContent side="left">
        <SheetHeader>
          <SheetTitle>Hunter</SheetTitle>
        </SheetHeader>
        <div className="flex-1 overflow-y-auto p-4">
          <TooltipProvider delayDuration={200}>
            <NavLinks items={items} orgSlug={orgSlug} onNavigate={() => setOpen(false)} />
          </TooltipProvider>
        </div>
      </SheetContent>
    </Sheet>
  );
}
