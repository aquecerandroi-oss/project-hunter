"use client";

import * as CheckboxPrimitive from "@radix-ui/react-checkbox";
import { Check } from "lucide-react";
import type { ComponentPropsWithoutRef, ElementRef } from "react";
import { forwardRef } from "react";

import { cn } from "@/lib/utils";

/**
 * shadcn-style Radix checkbox (T3.24a's brief §2, fixes C7/X6): the native
 * `<input type="checkbox">` in `radar-filters.tsx` had no themed focus ring
 * at all -- it fell back to the browser's own outline. `border-input`
 * (DESIGN-5, >= 3:1) draws the box itself; the checked state fills with
 * `gold` (docs/DESIGN.md §2 -- one of the rare, deliberate uses of gold as a
 * fill, mirroring the active-tab treatment) and the checkmark uses
 * `gold-fg` for contrast against it.
 */
export const Checkbox = forwardRef<
  ElementRef<typeof CheckboxPrimitive.Root>,
  ComponentPropsWithoutRef<typeof CheckboxPrimitive.Root>
>(function Checkbox({ className, ...props }, ref) {
  return (
    <CheckboxPrimitive.Root
      ref={ref}
      className={cn(
        "flex size-4 shrink-0 items-center justify-center rounded-sm border border-border-input bg-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold focus-visible:ring-offset-2 focus-visible:ring-offset-bg data-[state=checked]:border-gold data-[state=checked]:bg-gold",
        className,
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator className="flex items-center justify-center text-gold-fg">
        <Check className="size-3" aria-hidden="true" />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
});
