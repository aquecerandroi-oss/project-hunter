import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/**
 * Status vocabulary (docs/DESIGN.md §3): NORMAL -> `default` (neutral gray),
 * WATCHING -> `info`, ANOMALY -> `warning`, HOT -> `gold`, ENTRY_CANDIDATE ->
 * `positive`, BLOCKED_BY_RISK -> `negative`.
 */
export const badgeVariants = cva("inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium", {
  variants: {
    variant: {
      default: "border-transparent bg-bg-overlay text-fg",
      outline: "border-border bg-transparent text-fg",
      positive: "border-transparent bg-green/15 text-green",
      negative: "border-transparent bg-red/15 text-red",
      warning: "border-transparent bg-warning/15 text-warning",
      info: "border-transparent bg-info/15 text-info",
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
