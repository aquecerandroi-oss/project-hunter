import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export const badgeVariants = cva("inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium", {
  variants: {
    variant: {
      default: "border-transparent bg-surface-3 text-foreground",
      outline: "border-border bg-transparent text-foreground",
      positive: "border-transparent bg-positive/15 text-positive",
      negative: "border-transparent bg-negative/15 text-negative",
      warning: "border-transparent bg-warning/15 text-warning",
      planned: "border-dashed border-border bg-transparent text-muted",
    },
  },
  defaultVariants: { variant: "default" },
});

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
