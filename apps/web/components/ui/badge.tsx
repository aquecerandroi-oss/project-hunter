import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/**
 * Status vocabulary (docs/DESIGN.md §3): NORMAL -> `default` (neutral gray),
 * WATCHING -> `info`, ANOMALY -> `warning`, HOT -> `gold`, ENTRY_CANDIDATE ->
 * `positive`, BLOCKED_BY_RISK -> `negative`.
 *
 * DESIGN-5 (T3.23 audit, `.claude/state/design/2026-09-08/contrast-tokens.md`):
 * `positive`/`negative`/`warning`/`info` used to composite `bg-x/15` over
 * whatever background sat behind the badge -- that measured 4.34:1 (dark
 * `negative`) and 3.93:1 (light `positive`/`warning`), both below AA. Each
 * now uses the solid `-soft` token for that color instead, a fixed pair the
 * badge itself controls regardless of what it sits on top of.
 */
export const badgeVariants = cva("inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium", {
  variants: {
    variant: {
      default: "border-transparent bg-bg-overlay text-fg",
      outline: "border-border bg-transparent text-fg",
      positive: "border-transparent bg-green-soft text-green",
      negative: "border-transparent bg-red-soft text-red",
      warning: "border-transparent bg-warning-soft text-warning",
      info: "border-transparent bg-info-soft text-info",
      gold: "border-transparent bg-gold-soft text-gold",
      planned: "border-dashed border-border bg-transparent text-fg-muted",
    },
  },
  defaultVariants: { variant: "default" },
});

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
