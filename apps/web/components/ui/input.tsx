import { forwardRef, type InputHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/**
 * shadcn-style base input (T3.24a's brief §2, fixes C7/X6): `border-input`
 * (DESIGN-5, >= 3:1 against `bg-overlay`/`bg`) instead of the decorative
 * `border` token, `bg` (not `bg-overlay`) so the field reads as a hole in
 * the card rather than another surface, and the same gold focus ring every
 * other interactive control in the app uses.
 */
export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input(
  { className, ...props },
  ref,
) {
  return (
    <input
      ref={ref}
      className={cn(
        "h-8 rounded-md border border-border-input bg-bg px-2 text-[13px] text-fg placeholder:text-fg-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold focus-visible:ring-offset-2 focus-visible:ring-offset-bg",
        className,
      )}
      {...props}
    />
  );
});
