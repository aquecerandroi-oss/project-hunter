import { forwardRef, type SelectHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/**
 * shadcn-style base select (T3.24a's brief §2, fixes C7/X6). A native
 * `<select>` wrapped in the same visual/focus contract as `ui/input.tsx` --
 * the two call sites (`radar-filters.tsx`'s Regime/Tipo de anomalia) are
 * plain value/onChange dropdowns with no need for Radix's portal/listbox
 * machinery, so this stays the simplest thing that satisfies the contrast
 * and focus-ring rules rather than adding a second dependency for it.
 */
export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select(
  { className, children, ...props },
  ref,
) {
  return (
    <select
      ref={ref}
      className={cn(
        "h-8 rounded-md border border-border-input bg-bg px-2 text-[13px] text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold focus-visible:ring-offset-2 focus-visible:ring-offset-bg",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
});
